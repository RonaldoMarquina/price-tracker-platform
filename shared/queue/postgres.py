"""PostgreSQL-backed queue implementation using SELECT FOR UPDATE SKIP LOCKED."""

import json
import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from shared.queue.base import BaseQueue, QueueMessage
from shared.queue.models import LocalQueueMessage

logger = logging.getLogger("price-tracker.queue.postgres")


class PostgresQueue(BaseQueue):
    """Local persistent queue backed by PostgreSQL local_queue_messages table."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self.session_factory = session_factory

    def send_message(self, queue_name: str, message: BaseModel | dict[str, Any] | str) -> str:
        """Enqueue a message into PostgreSQL."""
        if isinstance(message, BaseModel):
            payload = message.model_dump(mode="json")
        elif isinstance(message, dict):
            payload = json.loads(json.dumps(message, default=str))
        else:
            payload = json.loads(message)

        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            msg = LocalQueueMessage(
                id=uuid.uuid4(),
                queue_name=queue_name,
                payload=payload,
                status="pending",
                attempts=0,
                visible_at=now,
                created_at=now,
            )
            session.add(msg)
            session.commit()
            logger.debug("Persisted queue message %s to queue %s", str(msg.id), queue_name)
            return str(msg.id)

    def receive_messages(
        self, queue_name: str, max_messages: int = 1, visibility_timeout: int = 30
    ) -> list[QueueMessage]:
        """Claim messages safely using SELECT ... FOR UPDATE SKIP LOCKED."""
        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            stmt = (
                select(LocalQueueMessage)
                .where(
                    LocalQueueMessage.queue_name == queue_name,
                    LocalQueueMessage.status.in_(["pending", "processing"]),
                    LocalQueueMessage.visible_at <= func.now(),
                )
                .order_by(LocalQueueMessage.created_at.asc())
                .limit(max_messages)
                .with_for_update(skip_locked=True)
            )
            rows = session.execute(stmt).scalars().all()
            if not rows:
                return []

            results: list[QueueMessage] = []
            for row in rows:
                handle = uuid.uuid4()
                row.receipt_handle = handle
                row.status = "processing"
                row.attempts += 1
                row.visible_at = now + timedelta(seconds=visibility_timeout)

                results.append(
                    QueueMessage(
                        message_id=str(row.id),
                        receipt_handle=str(handle),
                        body=json.dumps(row.payload),
                        attempts=row.attempts,
                        attributes={
                            "queue_name": row.queue_name,
                            "created_at": row.created_at.isoformat() if row.created_at else None,
                        },
                    )
                )

            session.commit()
            return results

    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        """Mark message as completed."""
        try:
            handle_uuid = uuid.UUID(receipt_handle)
        except ValueError:
            return

        with self.session_factory() as session:
            stmt = (
                update(LocalQueueMessage)
                .where(LocalQueueMessage.receipt_handle == handle_uuid)
                .values(
                    status="completed",
                    processed_at=func.now(),
                    receipt_handle=None,
                )
            )
            session.execute(stmt)
            session.commit()

    def change_message_visibility(
        self, queue_name: str, receipt_handle: str, visibility_timeout: int
    ) -> None:
        """Reset message to pending and adjust visible_at for retry."""
        try:
            handle_uuid = uuid.UUID(receipt_handle)
        except ValueError:
            return

        now = datetime.now(timezone.utc)
        with self.session_factory() as session:
            stmt = (
                update(LocalQueueMessage)
                .where(LocalQueueMessage.receipt_handle == handle_uuid)
                .values(
                    status="pending",
                    visible_at=now + timedelta(seconds=visibility_timeout),
                    receipt_handle=None,
                )
            )
            session.execute(stmt)
            session.commit()

    def send_to_dlq(
        self,
        dlq_name: str,
        message_payload: dict[str, Any] | str,
        error_reason: str,
        attempts: int,
        receipt_handle: str | None = None,
    ) -> str:
        """Transfer message to Dead Letter Queue."""
        handle_uuid = None
        if receipt_handle:
            try:
                handle_uuid = uuid.UUID(receipt_handle)
            except ValueError:
                handle_uuid = None

        with self.session_factory() as session:
            if handle_uuid:
                row = session.execute(
                    select(LocalQueueMessage).where(LocalQueueMessage.receipt_handle == handle_uuid)
                ).scalar_one_or_none()
                if row:
                    row.queue_name = dlq_name
                    row.status = "dlq"
                    row.error_reason = error_reason
                    row.processed_at = func.now()
                    row.receipt_handle = None
                    session.commit()
                    return str(row.id)

            if isinstance(message_payload, str):
                try:
                    payload = json.loads(message_payload)
                except Exception:
                    payload = {"raw": message_payload}
            else:
                payload = message_payload

            now = datetime.now(timezone.utc)
            dlq_msg = LocalQueueMessage(
                id=uuid.uuid4(),
                queue_name=dlq_name,
                payload=payload,
                status="dlq",
                attempts=attempts,
                error_reason=error_reason,
                visible_at=now,
                created_at=now,
                processed_at=now,
            )
            session.add(dlq_msg)
            session.commit()
            return str(dlq_msg.id)

    def get_queue_size(self, queue_name: str) -> int:
        """Return available messages count."""
        with self.session_factory() as session:
            count = session.execute(
                select(func.count(LocalQueueMessage.id)).where(
                    LocalQueueMessage.queue_name == queue_name,
                    LocalQueueMessage.status.in_(["pending", "processing"]),
                    LocalQueueMessage.visible_at <= func.now(),
                )
            ).scalar_one()
            return int(count)

    def purge_queue(self, queue_name: str) -> None:
        """Delete all messages in a queue (testing/cleanup)."""
        with self.session_factory() as session:
            session.execute(
                delete(LocalQueueMessage).where(LocalQueueMessage.queue_name == queue_name)
            )
            session.commit()
