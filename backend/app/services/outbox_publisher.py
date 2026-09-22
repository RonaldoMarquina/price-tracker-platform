"""Transactional Outbox Publisher for reliable SQS delivery with 3-phase execution."""

import json
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import ScrapingDlqLedger, ScrapingJob, ScrapingOutbox

logger = logging.getLogger("price-tracker.backend.outbox_publisher")

OUTBOX_MAX_ATTEMPTS = 5
OUTBOX_BASE_BACKOFF_SECONDS = 2
OUTBOX_MAX_BACKOFF_SECONDS = 60
OUTBOX_LEASE_DURATION_SECONDS = 30
OUTBOX_BATCH_SIZE = 10  # AWS SQS SendMessageBatch limit


def sanitize_error_text(code: str | None, message: str | None) -> str:
    """Sanitize error code and message preventing secret leakage and format issues."""
    safe_code = str(code or "UNKNOWN_ERROR").strip().replace("\n", " ")[:50]
    safe_msg = str(message or "").strip().replace("\n", " ")[:500]
    return f"{safe_code}: {safe_msg}".strip(": ")


class OutboxPublisherService:
    """Service orchestrating the claim, publication, and finalization of outbox messages."""

    def __init__(
        self,
        session_factory: sessionmaker,
        sqs_queue_service: Any,
        publisher_id: str | None = None,
        max_attempts: int = OUTBOX_MAX_ATTEMPTS,
        lease_duration_seconds: int = OUTBOX_LEASE_DURATION_SECONDS,
    ) -> None:
        self.session_factory = session_factory
        self.sqs = sqs_queue_service
        self.publisher_id = publisher_id or f"publisher-{uuid.uuid4().hex[:8]}"
        self.max_attempts = max_attempts
        self.lease_duration_seconds = lease_duration_seconds

    def claim_batch(self, batch_size: int = OUTBOX_BATCH_SIZE) -> list[dict[str, Any]]:
        """Phase A: Claim pending/failed or expired-lease outbox records with immediate commit."""
        now_ts = datetime.now(timezone.utc)
        lease_until = now_ts + timedelta(seconds=self.lease_duration_seconds)
        claimed_items: list[dict[str, Any]] = []

        with self.session_factory() as db:
            stmt = (
                select(ScrapingOutbox)
                .where(
                    (
                        ScrapingOutbox.status.in_(["pending", "failed"])
                        & (ScrapingOutbox.available_at <= now_ts)
                        & (ScrapingOutbox.attempts < self.max_attempts)
                    )
                    | (
                        (ScrapingOutbox.status == "publishing")
                        & (ScrapingOutbox.lease_until.is_not(None))
                        & (ScrapingOutbox.lease_until <= now_ts)
                    )
                )
                .order_by(ScrapingOutbox.id.asc())
                .with_for_update(skip_locked=True)
                .limit(batch_size)
            )
            rows = db.execute(stmt).scalars().all()
            if not rows:
                return []

            for r in rows:
                r.status = "publishing"
                r.locked_by = self.publisher_id
                r.locked_at = now_ts
                r.lease_until = lease_until
                claimed_items.append(
                    {
                        "id": r.id,
                        "aggregate_id": r.aggregate_id,
                        "event_type": r.event_type,
                        "source_ledger_id": r.source_ledger_id,
                        "queue_name": r.queue_name,
                        "payload": r.payload,
                        "attempts": r.attempts,
                        "idempotency_key": r.idempotency_key,
                    }
                )
            db.commit()  # Lock released immediately!

        return claimed_items

    def publish_batch(self, queue_name: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Phase B: Publish batch to SQS outside DB transaction."""
        if not items:
            return {"Successful": [], "Failed": []}

        entries = []
        for item in items:
            payload_str = json.dumps(item["payload"])
            entries.append(
                {
                    "Id": str(item["id"]),
                    "MessageBody": payload_str,
                }
            )

        try:
            return self.sqs.send_message_batch(queue_name, entries)
        except Exception as exc:
            logger.error("SQS batch publication exception: %s", exc)
            return {
                "Successful": [],
                "Failed": [
                    {
                        "Id": str(item["id"]),
                        "Code": "SQS_CLIENT_EXCEPTION",
                        "Message": str(exc),
                    }
                    for item in items
                ],
            }

    def finalize_batch(
        self,
        claimed_items: list[dict[str, Any]],
        sqs_response: dict[str, Any],
    ) -> dict[str, int]:
        """Phase C: Finalize batch state in RDS with short atomic transaction."""
        successful_list = sqs_response.get("Successful", [])
        failed_list = sqs_response.get("Failed", [])

        successful_map = {item["Id"]: item.get("MessageId") for item in successful_list}
        failed_map = {
            item["Id"]: (item.get("Code"), item.get("Message")) for item in failed_list
        }

        finalize_now = datetime.now(timezone.utc)
        published_count = 0
        failed_count = 0
        exhausted_count = 0

        with self.session_factory() as db:
            for item in claimed_items:
                item_id_str = str(item["id"])
                outbox_row = db.get(ScrapingOutbox, item["id"])
                if (
                    not outbox_row
                    or outbox_row.status != "publishing"
                    or outbox_row.locked_by != self.publisher_id
                ):
                    # Lease was lost or claimed by another worker; do not overwrite
                    continue

                if item_id_str in successful_map:
                    # Successful publication
                    outbox_row.status = "published"
                    outbox_row.published_at = finalize_now
                    outbox_row.provider_message_id = successful_map[item_id_str]
                    outbox_row.locked_by = None
                    outbox_row.locked_at = None
                    outbox_row.lease_until = None
                    outbox_row.last_error = None
                    published_count += 1

                    # Replay completion: update ledger replay_pending -> replayed
                    if (
                        item.get("event_type") == "replay"
                        and item.get("source_ledger_id")
                    ):
                        ledger_row = db.get(ScrapingDlqLedger, item["source_ledger_id"])
                        if ledger_row and ledger_row.status == "replay_pending":
                            ledger_row.status = "replayed"
                            ledger_row.replayed_at = finalize_now
                else:
                    # Failed publication or missing from response
                    if item_id_str in failed_map:
                        code, msg = failed_map[item_id_str]
                    else:
                        code, msg = "MISSING_FROM_RESPONSE", "Item missing from SQS response batch"

                    sanitized_err = sanitize_error_text(code, msg)
                    new_attempts = outbox_row.attempts + 1
                    outbox_row.attempts = new_attempts
                    outbox_row.last_error = sanitized_err
                    outbox_row.locked_by = None
                    outbox_row.locked_at = None
                    outbox_row.lease_until = None

                    if new_attempts >= self.max_attempts:
                        outbox_row.status = "exhausted"
                        exhausted_count += 1
                        logger.error(
                            "Outbox entry %s exhausted after %d attempts: %s",
                            item["id"],
                            new_attempts,
                            sanitized_err,
                        )

                        # Handle exhaustion compensations
                        if item.get("event_type") == "replay":
                            if item.get("source_ledger_id"):
                                ledger_row = db.get(ScrapingDlqLedger, item["source_ledger_id"])
                                if ledger_row and ledger_row.status == "replay_pending":
                                    ledger_row.status = "in_dlq"
                            job_row = db.get(ScrapingJob, item["aggregate_id"])
                            if job_row and job_row.status == "queued":
                                job_row.status = "dead_letter"
                                job_row.last_dlq_reason = "OUTBOX_REPLAY_EXHAUSTED"
                        else:
                            job_row = db.get(ScrapingJob, item["aggregate_id"])
                            if job_row and job_row.status == "queued":
                                job_row.status = "failed"
                                job_row.error_reason = "OUTBOX_PUBLISH_EXHAUSTED"
                    else:
                        outbox_row.status = "failed"
                        failed_count += 1
                        backoff = min(
                            OUTBOX_MAX_BACKOFF_SECONDS,
                            OUTBOX_BASE_BACKOFF_SECONDS * (2 ** (new_attempts - 1)),
                        )
                        jitter = random.uniform(0, 0.5 * backoff)
                        outbox_row.available_at = finalize_now + timedelta(
                            seconds=backoff + jitter
                        )

            db.commit()

        return {
            "published": published_count,
            "failed": failed_count,
            "exhausted": exhausted_count,
        }

    def process_cycle(
        self, queue_name: str, batch_size: int = OUTBOX_BATCH_SIZE
    ) -> dict[str, int]:
        """Execute a full 3-phase cycle."""
        claimed = self.claim_batch(batch_size=batch_size)
        if not claimed:
            return {"claimed": 0, "published": 0, "failed": 0, "exhausted": 0}

        sqs_resp = self.publish_batch(queue_name, claimed)
        results = self.finalize_batch(claimed, sqs_resp)
        results["claimed"] = len(claimed)
        return results


_running = True


def _handle_exit_signal(sig: int, frame: object) -> None:
    global _running
    logger.info("Termination signal %s received. Stopping outbox publisher loop...", sig)
    _running = False


def main() -> None:
    """Outbox publisher daemon process."""
    import os
    import signal
    import sys
    import time

    from app.core.queue import get_queue_service
    from app.db.session import SessionLocal

    signal.signal(signal.SIGINT, _handle_exit_signal)
    signal.signal(signal.SIGTERM, _handle_exit_signal)

    queue_name = os.getenv("QUEUE_NAME", "scraping-jobs")
    poll_interval = float(os.getenv("OUTBOX_POLL_INTERVAL", "2.0"))
    empty_interval = float(os.getenv("OUTBOX_EMPTY_INTERVAL", "5.0"))
    publisher_id = f"publisher-{os.uname().nodename}-{os.getpid()}"

    queue_service = get_queue_service()
    publisher = OutboxPublisherService(
        session_factory=SessionLocal,
        sqs_queue_service=queue_service,
        publisher_id=publisher_id,
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Outbox publisher started (id=%s, queue=%s).", publisher_id, queue_name)

    def _sleep(duration: float) -> None:
        elapsed = 0.0
        while _running and elapsed < duration:
            step = min(0.2, duration - elapsed)
            time.sleep(step)
            elapsed += step

    while _running:
        try:
            stats = publisher.process_cycle(queue_name=queue_name)
            if stats["claimed"] > 0:
                logger.info(
                    "Outbox cycle: claimed=%d published=%d failed=%d exhausted=%d",
                    stats["claimed"],
                    stats["published"],
                    stats["failed"],
                    stats["exhausted"],
                )
                _sleep(poll_interval)
            else:
                _sleep(empty_interval)
        except Exception as exc:
            logger.exception("Error in outbox publisher loop: %s", exc)
            _sleep(empty_interval)

    logger.info("Outbox publisher process stopped cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
