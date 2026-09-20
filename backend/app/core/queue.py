"""Queue provider for FastAPI backend services."""

from shared.queue.base import BaseQueue
from shared.queue.postgres import PostgresQueue

from app.db.session import SessionLocal

_postgres_queue = PostgresQueue(session_factory=SessionLocal)


def get_queue_service() -> BaseQueue:
    """Dependency provider returning the active queue service."""
    return _postgres_queue
