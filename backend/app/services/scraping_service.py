"""Service for orchestrating scraping jobs creation and enqueueing."""

import logging
import uuid
from datetime import datetime, timezone

from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ProductNotFoundError, StoreNotFoundError
from app.core.queue import BaseQueue, get_queue_service
from app.db.models import Product, ScrapingJob, Store
from app.schemas.scraping import ScrapingJobCreate, ScrapingJobResponse

logger = logging.getLogger("price-tracker.scraping")


class ScrapingService:
    """Handles validation and queueing of scraping jobs."""

    def __init__(self, queue: BaseQueue | None = None) -> None:
        self._queue = queue

    @property
    def queue(self) -> BaseQueue:
        if self._queue is None:
            self._queue = get_queue_service()
        return self._queue

    def create_scraping_job(self, db: Session, payload: ScrapingJobCreate) -> ScrapingJobResponse:
        """Validate request and push scraping job to queue."""
        # Validate store exists and is active
        store = db.execute(
            select(Store).where(Store.id == payload.store_id, Store.is_active.is_(True))
        ).scalar_one_or_none()

        if not store:
            raise StoreNotFoundError(str(payload.store_id))

        # Validate that all requested products exist and are active
        existing_products = (
            db.execute(
                select(Product.id).where(
                    Product.id.in_(payload.product_ids),
                    Product.is_active.is_(True),
                )
            )
            .scalars()
            .all()
        )

        existing_set = set(existing_products)
        missing_products = [pid for pid in payload.product_ids if pid not in existing_set]
        if missing_products:
            raise ProductNotFoundError(str(missing_products[0]))

        job_id = uuid.uuid4()
        now_utc = datetime.now(timezone.utc)

        # Build versioned message using shared contract
        message = ScrapingMessage(
            version=1,
            job_id=job_id,
            store_id=payload.store_id,
            product_ids=payload.product_ids,
            requested_at=now_utc,
            attempt=1,
        )

        job = ScrapingJob(
            id=job_id,
            store_id=payload.store_id,
            status="queued",
            trigger_type="manual",
            dispatch_slot=None,
            batch_size=len(payload.product_ids),
            observations_created=0,
            attempts=0,
            created_at=now_utc,
        )

        # Enqueue message and persist job atomically in the same transaction
        queue_name = "scraping-jobs"
        try:
            db.add(job)
            self.queue.send_message(queue_name, message, session=db)
            db.commit()
        except Exception:
            db.rollback()
            raise

        # Structured audit log
        logger.info(
            "JOB_QUEUED: job_id=%s store_id=%s products_count=%d queue=%s",
            str(job_id),
            str(payload.store_id),
            len(payload.product_ids),
            queue_name,
        )

        return ScrapingJobResponse(job_id=job_id, status="queued")


scraping_service = ScrapingService()
