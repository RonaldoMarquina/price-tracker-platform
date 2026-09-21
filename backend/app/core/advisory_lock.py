"""PostgreSQL session-level advisory locks using dedicated connections."""

import logging

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

logger = logging.getLogger("price-tracker.advisory-lock")

# Stable, documented 64-bit integer lock keys
DISPATCHER_SCHEDULED_LOCK_ID: int = 847291047
DISPATCHER_MANUAL_LOCK_ID: int = 847291048


class PostgresAdvisoryLock:
    """Manages session-level PostgreSQL advisory locks with a dedicated connection.

    Ensures distributed mutual exclusion across application instances and worker processes.
    Uses non-blocking pg_try_advisory_lock to prevent hanging.
    Guarantees lock release and connection cleanup in a finally block even on exceptions.
    """

    def __init__(self, engine: Engine, lock_id: int) -> None:
        self.engine = engine
        self.lock_id = lock_id
        self._conn: Connection | None = None
        self.acquired: bool = False

    def __enter__(self) -> bool:
        self._conn = self.engine.connect()
        try:
            result = self._conn.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": self.lock_id},
            ).scalar()
            self.acquired = bool(result)
            return self.acquired
        except Exception:
            self._cleanup()
            raise

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        try:
            if self._conn is not None and self.acquired:
                self._conn.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": self.lock_id},
                )
        except Exception as exc:
            logger.warning("Error releasing PostgreSQL advisory lock %s: %s", self.lock_id, exc)
        finally:
            self.acquired = False
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
