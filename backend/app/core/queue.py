import os

from shared.queue.base import BaseQueue
from shared.queue.postgres import PostgresQueue
from shared.queue.sqs import SqsQueue

from app.db.session import SessionLocal

_postgres_queue = PostgresQueue(session_factory=SessionLocal)
_sqs_queue: SqsQueue | None = None


def get_queue_service() -> BaseQueue:
    """Dependency provider returning the active queue service."""
    backend = os.getenv("QUEUE_BACKEND", "postgres").lower()
    if backend == "sqs":
        global _sqs_queue
        if _sqs_queue is None:
            _sqs_queue = SqsQueue()
        return _sqs_queue
    return _postgres_queue
