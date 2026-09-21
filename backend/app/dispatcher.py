"""Main entrypoint for Price Tracker Scheduled Dispatcher process."""

import logging
import os
import signal
import time

from app.db.session import SessionLocal, engine
from app.services.dispatch_service import DispatchService

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("price-tracker.dispatcher")

_running = True


def _handle_exit_signal(sig: int, frame: object) -> None:
    global _running
    logger.info("Termination signal %s received. Stopping dispatcher loop...", sig)
    _running = False


def main() -> None:
    """Scheduled dispatcher lifecycle loop."""
    signal.signal(signal.SIGINT, _handle_exit_signal)
    signal.signal(signal.SIGTERM, _handle_exit_signal)

    enabled_str = os.getenv("DISPATCHER_ENABLED", "false").strip().lower()
    enabled = enabled_str in ("true", "1", "yes")

    if not enabled:
        logger.info(
            "Dispatcher is disabled by configuration (DISPATCHER_ENABLED=%s). Exiting cleanly.",
            enabled_str,
        )
        return

    interval_seconds = int(os.getenv("DISPATCH_INTERVAL_SECONDS", "3600"))
    logger.info(
        "Dispatcher process started. Polling interval: %d seconds. Environment: %s",
        interval_seconds,
        os.getenv("ENVIRONMENT", "development"),
    )

    service = DispatchService(db_engine=engine, session_factory=SessionLocal)

    while _running:
        try:
            result = service.run_once()
            if result.skipped_lock:
                logger.debug("Scheduled dispatch skipped because another instance held the lock.")
            else:
                logger.info(
                    "Scheduled dispatch cycle completed: %d jobs created, %d products total.",
                    result.jobs_created,
                    result.total_products,
                )
        except Exception as exc:
            logger.exception("Unexpected error in scheduled dispatcher loop: %s", exc)

        # Sleep in 1-second increments to respond immediately to SIGINT / SIGTERM
        for _ in range(interval_seconds):
            if not _running:
                break
            time.sleep(1)

    logger.info("Dispatcher process stopped cleanly.")


if __name__ == "__main__":
    main()
