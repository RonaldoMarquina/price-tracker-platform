"""Main entrypoint for Price Tracker Scraping Worker."""

import logging
import os
import signal
import time

from shared.queue.postgres import PostgresQueue

from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.core.config import worker_settings
from app.db.session import SessionLocal
from app.repositories.observation_repository import ObservationRepository
from app.services.scraping_service import ScrapingWorkerService

logging.basicConfig(
    level=getattr(logging, worker_settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("price-tracker-worker")

_running = True


def _handle_exit_signal(sig: int, frame: object) -> None:
    global _running
    logger.info("Termination signal %s received. Stopping worker loop...", sig)
    _running = False


def get_worker_status() -> dict[str, str]:
    """Return status information about the worker process."""
    return {
        "status": "ready",
        "service": "worker",
        "environment": os.getenv("ENVIRONMENT", "development"),
    }


def create_consumer() -> ScrapingConsumer:
    """Instantiate a fully-wired ScrapingConsumer."""
    queue = PostgresQueue(session_factory=SessionLocal)
    adapter = FakeStoreAdapter()
    repo = ObservationRepository()
    service = ScrapingWorkerService(adapter=adapter, repository=repo)
    return ScrapingConsumer(
        queue=queue,
        service=service,
        session_factory=SessionLocal,
        queue_name=worker_settings.QUEUE_NAME,
        dlq_name=worker_settings.DLQ_NAME,
        max_retries=worker_settings.MAX_RETRIES,
        visibility_timeout=worker_settings.VISIBILITY_TIMEOUT,
    )


def main() -> None:
    """Worker polling lifecycle loop."""
    signal.signal(signal.SIGINT, _handle_exit_signal)
    signal.signal(signal.SIGTERM, _handle_exit_signal)

    logger.info(
        "Worker started. Environment: %s, Queue: %s, Max Retries: %d",
        worker_settings.ENVIRONMENT,
        worker_settings.QUEUE_NAME,
        worker_settings.MAX_RETRIES,
    )

    consumer = create_consumer()

    while _running:
        try:
            handled = consumer.process_next_message()
            if not handled:
                time.sleep(worker_settings.POLL_INTERVAL_SECONDS)
        except Exception as exc:
            logger.exception("Unexpected exception in worker loop: %s", exc)
            time.sleep(worker_settings.POLL_INTERVAL_SECONDS)

    logger.info("Worker process exited cleanly.")


if __name__ == "__main__":
    main()
