"""Service that drains the physical SQS DLQ, indexes to RDS ledger, and records quarantine."""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from shared.schemas.scraping import ScrapingMessage
from sqlalchemy.orm import sessionmaker

from app.db.models import ScrapingDlqLedger, ScrapingJob, ScrapingQuarantine, Store

logger = logging.getLogger("price-tracker.worker.dlq_indexer")


def hash_body(body: str) -> str:
    """Compute SHA-256 hash of message body string."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class DlqIndexerService:
    """Consumes physical SQS DLQ messages, populating ScrapingDlqLedger and draining the queue."""

    def __init__(
        self,
        session_factory: sessionmaker,
        sqs_queue_service: Any,
        dlq_name: str = "scraping-jobs-dlq",
    ) -> None:
        self.session_factory = session_factory
        self.sqs = sqs_queue_service
        self.dlq_name = dlq_name

    def process_cycle(self, max_messages: int = 10, visibility_timeout: int = 30) -> int:
        """Poll and index up to max_messages from physical SQS DLQ."""
        try:
            messages = self.sqs.receive_messages(
                queue_name=self.dlq_name,
                max_messages=max_messages,
                visibility_timeout=visibility_timeout,
            )
        except Exception as exc:
            logger.error("Failed to receive messages from DLQ '%s': %s", self.dlq_name, exc)
            return 0

        if not messages:
            return 0

        processed_count = 0
        for msg in messages:
            body_str = msg.body
            receipt_handle = msg.receipt_handle
            provider_id = msg.message_id
            attempts = msg.attempts
            body_sha = hash_body(body_str)

            # 1. Validación de Payload
            try:
                raw_json = json.loads(body_str)
                validated_msg = ScrapingMessage.model_validate(raw_json)
            except Exception as err:
                logger.error(
                    "Invalid payload in DLQ message %s. Quarantining. Error: %s",
                    provider_id,
                    err,
                )
                with self.session_factory() as db:
                    quarantine_entry = ScrapingQuarantine(
                        id=uuid.uuid4(),
                        provider_message_id=provider_id,
                        body_sha256=body_sha,
                        error_reason=str(err)[:500].replace("\n", " "),
                        quarantine_type="invalid_payload",
                        status="quarantined",
                        attempts=attempts,
                        received_at=datetime.now(timezone.utc),
                    )
                    db.add(quarantine_entry)
                    db.commit()

                # Eliminar de SQS DLQ tras confirmar en cuarentena
                try:
                    self.sqs.delete_message(self.dlq_name, receipt_handle)
                except Exception as del_exc:
                    logger.warning(
                        "Failed to delete quarantined message %s from SQS DLQ: %s",
                        provider_id,
                        del_exc,
                    )
                continue

            logical_id = validated_msg.logical_message_id
            job_id = validated_msg.job_id
            root_id = validated_msg.root_logical_message_id or logical_id
            replayed_from_id = validated_msg.replayed_from_message_id

            # 2. Redelivery Check: ¿Ya fue indexado previamente este logical_message_id?
            with self.session_factory() as db:
                existing_ledger = db.get(ScrapingDlqLedger, logical_id)
                if existing_ledger:
                    # Mensaje ya indexado (falló DeleteMessage anteriormente o redelivery)
                    # NO modificar ScrapingJob, NO sobrescribir error, NO alterar fechas
                    logger.info(
                        "DLQ message %s already indexed in ledger (status=%s). "
                        "Only deleting from SQS DLQ.",
                        logical_id,
                        existing_ledger.status,
                    )
                    try:
                        self.sqs.delete_message(self.dlq_name, receipt_handle)
                    except Exception as del_exc:
                        logger.warning(
                            "Failed to delete redelivered message %s from SQS DLQ: %s",
                            logical_id,
                            del_exc,
                        )
                    continue

                # 3. Validación de ScrapingJob
                job = db.get(ScrapingJob, job_id)
                if not job:
                    logger.error(
                        "ScrapingJob %s missing for DLQ message %s. Quarantining.",
                        job_id,
                        logical_id,
                    )
                    quarantine_entry = ScrapingQuarantine(
                        id=uuid.uuid4(),
                        provider_message_id=provider_id,
                        body_sha256=body_sha,
                        error_reason=f"ScrapingJob {job_id} not found in database",
                        quarantine_type="missing_job",
                        status="quarantined",
                        attempts=attempts,
                        received_at=datetime.now(timezone.utc),
                    )
                    db.add(quarantine_entry)
                    db.commit()
                    try:
                        self.sqs.delete_message(self.dlq_name, receipt_handle)
                    except Exception as del_exc:
                        logger.warning(
                            "Failed to delete missing-job message %s from SQS DLQ: %s",
                            provider_id,
                            del_exc,
                        )
                    continue

                # 4. Comprobación de estado terminal de éxito o descarte
                if job.status in ["completed", "skipped"]:
                    logger.info(
                        "ScrapingJob %s already in terminal state '%s'. "
                        "Dropping obsolete DLQ message %s without altering job.",
                        job_id,
                        job.status,
                        logical_id,
                    )
                    try:
                        self.sqs.delete_message(self.dlq_name, receipt_handle)
                    except Exception as del_exc:
                        logger.warning(
                            "Failed to delete obsolete DLQ message %s from SQS DLQ: %s",
                            logical_id,
                            del_exc,
                        )
                    continue

                # 5. Validación del ciclo lógico vigente
                active_logical_id = None
                if job.payload and isinstance(job.payload, dict):
                    raw_act = job.payload.get("logical_message_id")
                    if raw_act:
                        try:
                            active_logical_id = uuid.UUID(str(raw_act))
                        except ValueError:
                            active_logical_id = None

                is_active_mismatch = (
                    active_logical_id
                    and active_logical_id != logical_id
                    and job.status in ["queued", "processing"]
                )
                if is_active_mismatch:
                    # Mensaje obsoleto de un ciclo anterior (ej. trabajo ya reencolado)
                    logger.warning(
                        "DLQ message %s is obsolete for job %s (active cycle is %s). "
                        "Dropping without altering job.",
                        logical_id,
                        job_id,
                        active_logical_id,
                    )
                    try:
                        self.sqs.delete_message(self.dlq_name, receipt_handle)
                    except Exception as del_exc:
                        logger.warning(
                            "Failed to delete obsolete message %s from SQS DLQ: %s",
                            logical_id,
                            del_exc,
                        )
                    continue

                # 6. Fuente autoritativa de intentos y error
                # Worker persistió en ScrapingJob.attempts y error_reason
                authoritative_attempts = job.attempts if job.attempts > 0 else attempts
                authoritative_error = job.error_reason or "DLQ_RETRIES_EXHAUSTED"
                now_utc = datetime.now(timezone.utc)

                store_obj = db.get(Store, job.store_id)
                store_name = store_obj.name if store_obj else None

                # Inserción canónica en el ledger
                ledger_entry = ScrapingDlqLedger(
                    id=logical_id,
                    root_logical_message_id=root_id,
                    replayed_from_message_id=replayed_from_id,
                    job_id=job.id,
                    store_id=job.store_id,
                    store_name=store_name,
                    payload=validated_msg.model_dump(mode="json"),
                    products_count=len(validated_msg.product_ids),
                    attempts=authoritative_attempts,
                    error_reason=authoritative_error[:500],
                    sent_to_dlq_at=now_utc,
                    status="in_dlq",
                    replay_count=job.replay_count,
                    created_at=now_utc,
                )
                db.add(ledger_entry)

                # Transición de ScrapingJob a dead_letter
                job.status = "dead_letter"
                job.sent_to_dlq_at = now_utc
                job.last_dlq_reason = authoritative_error[:500]

                db.commit()

            # 7. Borrado físico en SQS DLQ solo tras commit exitoso
            try:
                self.sqs.delete_message(self.dlq_name, receipt_handle)
            except Exception as del_exc:
                logger.warning(
                    "Failed to delete message %s from SQS DLQ after commit: %s",
                    logical_id,
                    del_exc,
                )

            processed_count += 1

        return processed_count


_running = True


def _handle_exit_signal(sig: int, frame: object) -> None:
    global _running
    logger.info("Termination signal %s received. Stopping DLQ indexer loop...", sig)
    _running = False


def main() -> None:
    """DLQ indexer daemon process."""
    import os
    import signal
    import sys
    import time

    from shared.queue.sqs import SqsQueue

    from app.db.session import SessionLocal

    signal.signal(signal.SIGINT, _handle_exit_signal)
    signal.signal(signal.SIGTERM, _handle_exit_signal)

    dlq_name = os.getenv("DLQ_NAME", "scraping-jobs-dlq")
    poll_interval = float(os.getenv("DLQ_POLL_INTERVAL", "5.0"))
    empty_interval = float(os.getenv("DLQ_EMPTY_INTERVAL", "15.0"))

    sqs_service = SqsQueue()
    indexer = DlqIndexerService(
        session_factory=SessionLocal,
        sqs_queue_service=sqs_service,
        dlq_name=dlq_name,
    )

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("DLQ indexer started (dlq_name=%s).", dlq_name)

    def _sleep(duration: float) -> None:
        elapsed = 0.0
        while _running and elapsed < duration:
            step = min(0.2, duration - elapsed)
            time.sleep(step)
            elapsed += step

    while _running:
        try:
            processed = indexer.process_cycle(max_messages=10)
            if processed > 0:
                logger.info("DLQ indexer processed %d messages.", processed)
                _sleep(poll_interval)
            else:
                _sleep(empty_interval)
        except Exception as exc:
            logger.exception("Error in DLQ indexer loop: %s", exc)
            _sleep(empty_interval)

    logger.info("DLQ indexer process stopped cleanly.")
    sys.exit(0)


if __name__ == "__main__":
    main()
