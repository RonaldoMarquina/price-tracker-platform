"""Scraping consumer that pulls messages from PostgreSQL queue and orchestrates execution."""

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime, timezone

from shared.queue.base import BaseQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.base import (
    FatalScrapingError,
    StoreBlockedError,
    StoreDisabledError,
    TerminalInternalError,
    TransientScrapingError,
)
from app.db.models import ScrapingJob
from app.services.scraping_service import ScrapingWorkerService

logger = logging.getLogger("price-tracker.worker.consumer")


class InvalidStateTransitionError(Exception):
    """Raised when an illegal ScrapingJob status transition is attempted."""

    pass


# Allowed state machine transitions for normal consumer processing.
# NOTE: Transition 'dead_letter' -> 'queued' is strictly excluded here
# and is authorized ONLY in the replay service (Subincrement 7C).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"processing"},
    "processing": {"completed", "retrying", "skipped", "failed", "dead_letter", "processing"},
    "retrying": {"processing"},
}


def sanitize_error(error: str | Exception | None, max_length: int = 500) -> str | None:
    """Sanitize and truncate error string to avoid storing unbounded text, headers, or secrets."""
    if error is None:
        return None
    text = str(error).strip()
    # Remove Authorization headers / Bearer tokens
    text = re.sub(r"(?i)authorization:\s*(?:bearer\s+)?[^\s]+", "[REDACTED_AUTH]", text)
    text = re.sub(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "[REDACTED_TOKEN]", text)
    # Remove stack traces
    text = re.sub(
        r"(?i)traceback\s*\(most\s+recent\s+call\s+last\):.*",
        "[TRACEBACK_REDACTED]",
        text,
        flags=re.DOTALL,
    )
    lines = text.splitlines()
    cleaned = " ".join(line.strip() for line in lines if line.strip())
    if len(cleaned) > max_length:
        return cleaned[: max_length - 3] + "..."
    return cleaned or None


def transition_job_status(
    job: ScrapingJob,
    target_status: str,
    *,
    error_reason: str | None = None,
    observations_created: int | None = None,
    is_recovery: bool = False,
) -> None:
    """Validate and apply a status transition for ScrapingJob."""
    current = job.status
    if is_recovery and current == "processing" and target_status == "processing":
        # Permitted recovery of an abandoned processing job after visibility timeout
        pass
    elif target_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(
            f"Invalid transition from '{current}' to '{target_status}' for ScrapingJob {job.id}"
        )

    now = datetime.now(timezone.utc)
    job.status = target_status

    if target_status == "processing":
        if job.started_at is None:
            job.started_at = now
    elif target_status in ("completed", "skipped", "failed", "dead_letter"):
        job.finished_at = now
        if target_status == "dead_letter":
            job.sent_to_dlq_at = now
            if error_reason is not None:
                job.last_dlq_reason = sanitize_error(error_reason)

    if observations_created is not None:
        job.observations_created = (job.observations_created or 0) + observations_created

    if error_reason is not None:
        job.error_reason = sanitize_error(error_reason)


class ScrapingConsumer:
    """Consumes scraping job messages from persistent queue, handling retries and DLQ."""

    def __init__(
        self,
        queue: BaseQueue,
        service: ScrapingWorkerService,
        session_factory: Callable[[], Session],
        queue_name: str = "scraping-jobs",
        dlq_name: str = "scraping-jobs-dlq",
        max_retries: int = 3,
        visibility_timeout: int = 30,
    ) -> None:
        self.queue = queue
        self.service = service
        self.session_factory = session_factory
        self.queue_name = queue_name
        self.dlq_name = dlq_name
        self.max_retries = max_retries
        self.visibility_timeout = visibility_timeout

    def process_next_message(self) -> bool:
        """Fetch and process a message from the queue. Returns True if a message was handled."""
        messages = self.queue.receive_messages(
            self.queue_name, max_messages=1, visibility_timeout=self.visibility_timeout
        )
        if not messages:
            return False

        msg = messages[0]
        # The database column 'attempts' is the single source of truth
        attempts = msg.attempts

        # 1. Parse and validate schema
        try:
            raw_data = json.loads(msg.body)
            scraping_msg = ScrapingMessage.model_validate(raw_data)
        except Exception as exc:
            logger.error(
                "JOB_SENT_TO_DLQ: message_id=%s reason=INVALID_SCHEMA attempts=%d error=%s",
                msg.message_id,
                attempts,
                str(exc),
            )
            self.queue.send_to_dlq(
                self.dlq_name,
                message_payload=msg.body,
                error_reason=sanitize_error(f"INVALID_SCHEMA: {exc}") or "INVALID_SCHEMA",
                attempts=attempts,
                receipt_handle=msg.receipt_handle,
            )
            return True

        logger.info(
            "JOB_PROCESSING: job_id=%s store_id=%s attempt=%d",
            str(scraping_msg.job_id),
            str(scraping_msg.store_id),
            attempts,
        )

        with self.session_factory() as db:
            result = db.execute(
                select(ScrapingJob)
                .where(ScrapingJob.id == scraping_msg.job_id)
                .with_for_update()
            )
            job = result.scalar_one_or_none()
            if not isinstance(job, ScrapingJob):
                job = None

            now = datetime.now(timezone.utc)
            if job is None:
                # Reconcile legacy message missing a prior ScrapingJob
                logger.info(
                    "RECONCILING_LEGACY_JOB: job_id=%s store_id=%s attempt=%d",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                )
                job = ScrapingJob(
                    id=scraping_msg.job_id,
                    store_id=scraping_msg.store_id,
                    status="processing",
                    trigger_type="manual",
                    dispatch_slot=None,
                    batch_size=len(scraping_msg.product_ids),
                    observations_created=0,
                    attempts=attempts,
                    payload=scraping_msg.model_dump(mode="json"),
                    created_at=scraping_msg.requested_at or now,
                    started_at=now,
                )
                db.add(job)
                db.commit()
                db.refresh(job)
            else:
                # If already in terminal completed/skipped state, acknowledge idempotently
                if job.status in ["completed", "skipped"]:
                    logger.info(
                        "JOB_ALREADY_TERMINAL: job_id=%s store_id=%s attempt=%d status=%s",
                        str(scraping_msg.job_id),
                        str(scraping_msg.store_id),
                        attempts,
                        job.status,
                    )
                    self.queue.delete_message(self.queue_name, msg.receipt_handle)
                    return True

                # Check if another worker is actively processing this job
                if job.status == "processing" and job.started_at:
                    elapsed = (now - job.started_at).total_seconds()
                    if elapsed < self.visibility_timeout:
                        logger.warning(
                            "JOB_CONCURRENT_PROCESSING: job_id=%s already processing "
                            "(elapsed=%.1fs < %ds)",
                            str(scraping_msg.job_id),
                            elapsed,
                            self.visibility_timeout,
                        )
                        return True

                is_recovery = job.status == "processing"
                job.attempts = attempts
                if not job.payload:
                    job.payload = scraping_msg.model_dump(mode="json")
                transition_job_status(job, "processing", is_recovery=is_recovery)
                db.commit()


            try:
                inserted_count = self.service.process_job(db=db, message=scraping_msg)
                # Successful execution -> transition to completed
                transition_job_status(job, "completed", observations_created=inserted_count)
                job.attempts = attempts
                job.error_reason = None
                db.commit()

                # Acknowledge and mark completed in queue
                self.queue.delete_message(self.queue_name, msg.receipt_handle)
                logger.info(
                    "JOB_SUCCESS: job_id=%s store_id=%s attempt=%d "
                    "observations_created=%d status=completed",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    inserted_count,
                )
                return True
            except StoreDisabledError as exc:
                skip_reason = f"SKIPPED_STORE_DISABLED: {exc}"
                transition_job_status(job, "skipped", error_reason=skip_reason)
                job.attempts = attempts
                db.commit()

                self.queue.delete_message(
                    self.queue_name, msg.receipt_handle, error_reason=skip_reason
                )
                logger.warning(
                    "JOB_SKIPPED: job_id=%s store_id=%s attempt=%d reason=STORE_DISABLED error=%s",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    str(exc),
                )
                return True
            except StoreBlockedError as exc:
                skip_reason = f"SKIPPED_STORE_BLOCKED: {exc}"
                transition_job_status(job, "skipped", error_reason=skip_reason)
                job.attempts = attempts
                db.commit()

                self.queue.delete_message(
                    self.queue_name, msg.receipt_handle, error_reason=skip_reason
                )
                logger.warning(
                    "JOB_SKIPPED_BLOCKED: job_id=%s store_id=%s attempt=%d "
                    "reason=STORE_BLOCKED error=%s",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    str(exc),
                )
                return True
            except TerminalInternalError as exc:
                fail_reason = f"FAILED_TERMINAL_ERROR: {exc}"
                transition_job_status(job, "failed", error_reason=fail_reason)
                job.attempts = attempts
                db.commit()

                self.queue.delete_message(
                    self.queue_name, msg.receipt_handle, error_reason=fail_reason
                )
                logger.error(
                    "JOB_FAILED: job_id=%s store_id=%s attempt=%d "
                    "reason=FAILED_TERMINAL_ERROR error=%s",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    str(exc),
                )
                return True
            except FatalScrapingError as exc:
                dlq_reason = f"FATAL_SCRAPING_ERROR: {exc}"
                transition_job_status(job, "dead_letter", error_reason=dlq_reason)
                job.attempts = attempts
                db.commit()

                self.queue.send_to_dlq(
                    self.dlq_name,
                    message_payload=msg.body,
                    error_reason=sanitize_error(dlq_reason) or "FATAL_SCRAPING_ERROR",
                    attempts=attempts,
                    receipt_handle=msg.receipt_handle,
                )
                logger.error(
                    "JOB_SENT_TO_DLQ: job_id=%s store_id=%s attempt=%d "
                    "reason=FATAL_SCRAPING_ERROR error=%s",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    str(exc),
                )
                return True
            except TransientScrapingError as exc:
                if attempts < self.max_retries:
                    retry_reason = f"TRANSIENT_ERROR: {exc}"
                    transition_job_status(job, "retrying", error_reason=retry_reason)
                    job.attempts = attempts
                    db.commit()

                    backoff = min(60, 2 * attempts)
                    self.queue.change_message_visibility(
                        self.queue_name, msg.receipt_handle, visibility_timeout=backoff
                    )
                    logger.warning(
                        "JOB_RETRYING: job_id=%s store_id=%s attempt=%d "
                        "max_retries=%d error=%s backoff_seconds=%d",
                        str(scraping_msg.job_id),
                        str(scraping_msg.store_id),
                        attempts,
                        self.max_retries,
                        str(exc),
                        backoff,
                    )
                else:
                    dlq_reason = f"MAX_RETRIES_EXCEEDED: {exc}"
                    transition_job_status(job, "dead_letter", error_reason=dlq_reason)
                    job.attempts = attempts
                    db.commit()

                    self.queue.send_to_dlq(
                        self.dlq_name,
                        message_payload=msg.body,
                        error_reason=sanitize_error(dlq_reason) or "MAX_RETRIES_EXCEEDED",
                        attempts=attempts,
                        receipt_handle=msg.receipt_handle,
                    )
                    logger.error(
                        "JOB_SENT_TO_DLQ: job_id=%s store_id=%s attempt=%d "
                        "max_retries=%d reason=MAX_RETRIES_EXCEEDED",
                        str(scraping_msg.job_id),
                        str(scraping_msg.store_id),
                        attempts,
                        self.max_retries,
                    )
                return True
            except Exception as exc:
                dlq_reason = f"UNEXPECTED_ERROR: {exc}"
                transition_job_status(job, "dead_letter", error_reason=dlq_reason)
                job.attempts = attempts
                db.commit()

                self.queue.send_to_dlq(
                    self.dlq_name,
                    message_payload=msg.body,
                    error_reason=sanitize_error(dlq_reason) or "UNEXPECTED_ERROR",
                    attempts=attempts,
                    receipt_handle=msg.receipt_handle,
                )
                logger.error(
                    "JOB_SENT_TO_DLQ: job_id=%s store_id=%s attempt=%d "
                    "reason=UNEXPECTED_ERROR error=%s",
                    str(scraping_msg.job_id),
                    str(scraping_msg.store_id),
                    attempts,
                    str(exc),
                )
                return True
