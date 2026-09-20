"""Scraping consumer that pulls messages from PostgreSQL queue and orchestrates execution."""

import json
import logging
from collections.abc import Callable

from shared.queue.base import BaseQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy.orm import Session

from app.adapters.base import TransientScrapingError
from app.services.scraping_service import ScrapingWorkerService

logger = logging.getLogger("price-tracker.worker.consumer")


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
                error_reason=f"INVALID_SCHEMA: {exc}",
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
            try:
                inserted_count = self.service.process_job(db=db, message=scraping_msg)
                # Successful execution -> Acknowledge and mark completed
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
            except TransientScrapingError as exc:
                if attempts < self.max_retries:
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
                    self.queue.send_to_dlq(
                        self.dlq_name,
                        message_payload=msg.body,
                        error_reason=f"MAX_RETRIES_EXCEEDED: {exc}",
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
                self.queue.send_to_dlq(
                    self.dlq_name,
                    message_payload=msg.body,
                    error_reason=f"UNEXPECTED_ERROR: {exc}",
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
