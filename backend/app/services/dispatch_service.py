"""Service orchestrating scheduled and manual scraping dispatch, job listing, and queue metrics."""

import logging
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from shared.adapters.store_capabilities import is_store_dispatchable
from shared.queue.base import BaseQueue
from shared.schemas.scraping import ScrapingMessage
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.advisory_lock import (
    DISPATCHER_MANUAL_LOCK_ID,
    DISPATCHER_SCHEDULED_LOCK_ID,
    PostgresAdvisoryLock,
)
from app.core.queue import get_queue_service
from app.db.models import Product, ScrapingJob, Store, StoreProduct
from app.db.session import SessionLocal, engine
from app.schemas.scraping import (
    ManualDispatchResponse,
    ScrapingJobDetailResponse,
    ScrapingJobListResponse,
    ScrapingMetricsResponse,
)

logger = logging.getLogger("price-tracker.dispatch")


def sanitize_error(msg: str | None, max_len: int = 500) -> str | None:
    """Sanitize and truncate error reason to avoid leaking sensitive internal traces."""
    if not msg:
        return None
    cleaned = re.sub(r"\s+", " ", msg).strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "..."
    return cleaned


@dataclass
class DispatchRunResult:
    """Result of a scheduled or manual dispatch execution."""

    skipped_lock: bool = False
    jobs_created: int = 0
    total_products: int = 0
    job_ids: list[uuid.UUID] = field(default_factory=list)
    skipped_stores: list[uuid.UUID] = field(default_factory=list)
    failed_stores: list[uuid.UUID] = field(default_factory=list)


class DispatchService:
    """Handles deterministic job dispatching, queries, and operational queue metrics."""

    def __init__(
        self,
        db_engine: Engine | None = None,
        session_factory: sessionmaker[Session] | None = None,
        queue: BaseQueue | None = None,
    ) -> None:
        self.engine = db_engine or engine
        self.session_factory = session_factory or SessionLocal
        self._queue = queue

    @property
    def queue(self) -> BaseQueue:
        if self._queue is None:
            self._queue = get_queue_service()
        return self._queue

    def run_once(
        self,
        slot: datetime | None = None,
        allow_offline_adapters: bool = False,
    ) -> DispatchRunResult:
        """Run a single deterministic scheduled dispatch pass protected by an advisory lock.

        Args:
            slot: Specific UTC timestamp slot to assign. If None, current hour is used.
            allow_offline_adapters: Allow fake offline adapter for testing.

        Returns:
            DispatchRunResult summarizing created, skipped, and failed jobs.
        """
        # 1. Normalize slot to UTC with zero seconds/microseconds
        now_utc = datetime.now(timezone.utc)
        if slot is None:
            normalized_slot = now_utc.replace(minute=0, second=0, microsecond=0)
        else:
            if slot.tzinfo is None:
                normalized_slot = slot.replace(tzinfo=timezone.utc)
            else:
                normalized_slot = slot.astimezone(timezone.utc)
            normalized_slot = normalized_slot.replace(second=0, microsecond=0)

        # 2. Acquire non-blocking advisory lock on dedicated connection
        with PostgresAdvisoryLock(self.engine, DISPATCHER_SCHEDULED_LOCK_ID) as locked:
            if not locked:
                logger.info(
                    "Scheduled dispatcher lock %s is held by another process. Skipping cleanly.",
                    DISPATCHER_SCHEDULED_LOCK_ID,
                )
                return DispatchRunResult(skipped_lock=True)

            logger.info("Executing scheduled dispatch for slot: %s", normalized_slot.isoformat())

            result = DispatchRunResult()

            # 3. Query active candidate stores
            with self.session_factory() as db:
                candidate_stores = (
                    db.execute(select(Store).where(Store.is_active.is_(True)).order_by(Store.name.asc()))
                    .scalars()
                    .all()
                )

            # 4. Dispatch each store in an independent transaction
            for store in candidate_stores:
                is_dispatchable, reason = is_store_dispatchable(
                    store.domain, allow_offline=allow_offline_adapters
                )
                if not is_dispatchable:
                    logger.info(
                        "Store '%s' (%s) skipped from dispatch: %s",
                        store.name,
                        store.domain,
                        reason,
                    )
                    result.skipped_stores.append(store.id)
                    continue

                # Open isolated transaction for this store
                with self.session_factory() as store_tx:
                    try:
                        # Check idempotent slot uniqueness
                        existing_slot_job = store_tx.execute(
                            select(ScrapingJob.id).where(
                                ScrapingJob.store_id == store.id,
                                ScrapingJob.dispatch_slot == normalized_slot,
                            )
                        ).scalar_one_or_none()

                        if existing_slot_job:
                            logger.info(
                                "Store '%s' already dispatched for slot %s. Skipping idempotently.",
                                store.name,
                                normalized_slot.isoformat(),
                            )
                            result.skipped_stores.append(store.id)
                            continue

                        # Find active store products linked to active catalog products
                        product_ids = (
                            store_tx.execute(
                                select(StoreProduct.product_id)
                                .join(Product, StoreProduct.product_id == Product.id)
                                .where(
                                    StoreProduct.store_id == store.id,
                                    StoreProduct.is_active.is_(True),
                                    Product.is_active.is_(True),
                                )
                                .order_by(StoreProduct.product_id.asc())
                            )
                            .scalars()
                            .all()
                        )

                        if not product_ids:
                            logger.info(
                                "Store '%s' has no active product associations. Skipping.",
                                store.name,
                            )
                            result.skipped_stores.append(store.id)
                            continue

                        # Atomic job + queue message creation
                        job_id = uuid.uuid4()
                        job_created_at = datetime.now(timezone.utc)

                        job = ScrapingJob(
                            id=job_id,
                            store_id=store.id,
                            status="queued",
                            trigger_type="scheduled",
                            dispatch_slot=normalized_slot,
                            batch_size=len(product_ids),
                            observations_created=0,
                            attempts=0,
                            created_at=job_created_at,
                        )
                        store_tx.add(job)

                        message = ScrapingMessage(
                            version=1,
                            job_id=job_id,
                            store_id=store.id,
                            product_ids=product_ids,
                            requested_at=job_created_at,
                            attempt=1,
                        )
                        self.queue.send_message("scraping-jobs", message, session=store_tx)

                        store_tx.commit()

                        result.jobs_created += 1
                        result.total_products += len(product_ids)
                        result.job_ids.append(job_id)

                        logger.info(
                            "SCHEDULED_JOB_DISPATCHED: job_id=%s store='%s' products=%d slot=%s",
                            str(job_id),
                            store.name,
                            len(product_ids),
                            normalized_slot.isoformat(),
                        )

                    except IntegrityError as exc:
                        store_tx.rollback()
                        is_slot_dup = (
                            "uq_scraping_jobs_store_dispatch_slot" in str(exc)
                            or getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                            == "uq_scraping_jobs_store_dispatch_slot"
                        )
                        if is_slot_dup:
                            logger.info(
                                "Duplicate slot for store '%s'. Skipping idempotently.",
                                store.name,
                            )
                            result.skipped_stores.append(store.id)
                        else:
                            logger.error(
                                "Integrity error for store '%s': %s",
                                store.name,
                                sanitize_error(str(exc)),
                            )
                            result.failed_stores.append(store.id)
                    except Exception as exc:
                        store_tx.rollback()
                        logger.error(
                            "Failed to dispatch store '%s': %s",
                            store.name,
                            sanitize_error(str(exc)),
                        )
                        result.failed_stores.append(store.id)

            return result

    def dispatch_manual(
        self,
        store_id: uuid.UUID | None = None,
        allow_offline_adapters: bool = False,
    ) -> ManualDispatchResponse:
        """Trigger an immediate manual dispatch execution with concurrency protection.

        Args:
            store_id: Optional specific store. If None, all active stores are dispatched.
            allow_offline_adapters: Allow fake store adapter for test verification.

        Returns:
            ManualDispatchResponse with details of created, skipped, and failed stores.

        Raises:
            HTTPException 409: If another manual dispatch is concurrently in progress.
            HTTPException 404: If requested store_id does not exist.
            HTTPException 422: If requested store_id is inactive or has no active adapter.
        """
        with PostgresAdvisoryLock(self.engine, DISPATCHER_MANUAL_LOCK_ID) as locked:
            if not locked:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Una solicitud de despacho manual ya se encuentra en ejecución.",
                )

            with self.session_factory() as db:
                if store_id is not None:
                    target_store = db.execute(
                        select(Store).where(Store.id == store_id)
                    ).scalar_one_or_none()

                    if not target_store:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"Tienda no encontrada: {store_id}",
                        )

                    if not target_store.is_active:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=f"La tienda '{target_store.name}' está desactivada.",
                        )

                    is_disp, reason = is_store_dispatchable(
                        target_store.domain, allow_offline=allow_offline_adapters
                    )
                    if not is_disp:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail=(
                                f"La tienda '{target_store.name}' no tiene un adaptador "
                                f"habilitado ({reason})."
                            ),
                        )

                    candidate_stores = [target_store]
                else:
                    candidate_stores = (
                        db.execute(
                            select(Store).where(Store.is_active.is_(True)).order_by(Store.name.asc())
                        )
                        .scalars()
                        .all()
                    )

            created_jobs: list[uuid.UUID] = []
            total_products = 0
            skipped_stores: list[uuid.UUID] = []
            failed_stores: list[uuid.UUID] = []

            for store in candidate_stores:
                is_disp, reason = is_store_dispatchable(
                    store.domain, allow_offline=allow_offline_adapters
                )
                if not is_disp:
                    logger.info(
                        "Store '%s' skipped in manual dispatch: %s", store.name, reason
                    )
                    skipped_stores.append(store.id)
                    continue

                with self.session_factory() as store_tx:
                    try:
                        product_ids = (
                            store_tx.execute(
                                select(StoreProduct.product_id)
                                .join(Product, StoreProduct.product_id == Product.id)
                                .where(
                                    StoreProduct.store_id == store.id,
                                    StoreProduct.is_active.is_(True),
                                    Product.is_active.is_(True),
                                )
                                .order_by(StoreProduct.product_id.asc())
                            )
                            .scalars()
                            .all()
                        )

                        if not product_ids:
                            logger.info(
                                "Store '%s' has no active product associations. Skipping.",
                                store.name,
                            )
                            skipped_stores.append(store.id)
                            continue

                        job_id = uuid.uuid4()
                        job_created_at = datetime.now(timezone.utc)

                        job = ScrapingJob(
                            id=job_id,
                            store_id=store.id,
                            status="queued",
                            trigger_type="manual",
                            dispatch_slot=None,
                            batch_size=len(product_ids),
                            observations_created=0,
                            attempts=0,
                            created_at=job_created_at,
                        )
                        store_tx.add(job)

                        message = ScrapingMessage(
                            version=1,
                            job_id=job_id,
                            store_id=store.id,
                            product_ids=product_ids,
                            requested_at=job_created_at,
                            attempt=1,
                        )
                        self.queue.send_message("scraping-jobs", message, session=store_tx)

                        store_tx.commit()

                        created_jobs.append(job_id)
                        total_products += len(product_ids)

                        logger.info(
                            "MANUAL_JOB_DISPATCHED: job_id=%s store='%s' products=%d",
                            str(job_id),
                            store.name,
                            len(product_ids),
                        )

                    except Exception as exc:
                        store_tx.rollback()
                        logger.error(
                            "Failed manual dispatch for store '%s': %s",
                            store.name,
                            sanitize_error(str(exc)),
                        )
                        failed_stores.append(store.id)

            return ManualDispatchResponse(
                jobs_created=len(created_jobs),
                total_products=total_products,
                job_ids=created_jobs,
                skipped_stores=skipped_stores,
                failed_stores=failed_stores,
            )

    def list_jobs(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        status_filter: str | None = None,
        store_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> ScrapingJobListResponse:
        """List scraping jobs with pagination, filtering, and deterministic sorting."""
        if from_date is not None and to_date is not None and from_date > to_date:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="'from_date' cannot be later than 'to_date'.",
            )

        query = (
            select(ScrapingJob, Store.name.label("store_name"))
            .join(Store, ScrapingJob.store_id == Store.id)
        )

        if status_filter:
            query = query.where(ScrapingJob.status == status_filter)
        if store_id:
            query = query.where(ScrapingJob.store_id == store_id)
        if from_date:
            query = query.where(ScrapingJob.created_at >= from_date)
        if to_date:
            query = query.where(ScrapingJob.created_at <= to_date)

        # Count total matching rows
        count_stmt = select(func.count()).select_from(query.subquery())
        total = db.execute(count_stmt).scalar() or 0

        # Deterministic sorting created_at DESC, id DESC
        paginated_query = (
            query.order_by(ScrapingJob.created_at.desc(), ScrapingJob.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = db.execute(paginated_query).all()

        items = []
        for job, store_name in rows:
            items.append(
                ScrapingJobDetailResponse(
                    id=job.id,
                    store_id=job.store_id,
                    store_name=store_name,
                    status=job.status,
                    trigger_type=job.trigger_type,
                    dispatch_slot=job.dispatch_slot,
                    batch_size=job.batch_size,
                    observations_created=job.observations_created,
                    attempts=job.attempts,
                    error_reason=sanitize_error(job.error_reason),
                    created_at=job.created_at,
                    started_at=job.started_at,
                    finished_at=job.finished_at,
                )
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 0

        return ScrapingJobListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def get_job(self, db: Session, job_id: uuid.UUID) -> ScrapingJobDetailResponse:
        """Retrieve single scraping job detail. Raises 404 if not found."""
        row = db.execute(
            select(ScrapingJob, Store.name.label("store_name"))
            .join(Store, ScrapingJob.store_id == Store.id)
            .where(ScrapingJob.id == job_id)
        ).one_or_none()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Trabajo de scraping no encontrado: {job_id}",
            )

        job, store_name = row
        return ScrapingJobDetailResponse(
            id=job.id,
            store_id=job.store_id,
            store_name=store_name,
            status=job.status,
            trigger_type=job.trigger_type,
            dispatch_slot=job.dispatch_slot,
            batch_size=job.batch_size,
            observations_created=job.observations_created,
            attempts=job.attempts,
            error_reason=sanitize_error(job.error_reason),
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def get_queue_metrics(self, db: Session, window_hours: int = 24) -> ScrapingMetricsResponse:
        """Calculate live queue metrics and historical scraping performance."""
        now_utc = datetime.now(timezone.utc)
        window_start = now_utc - timedelta(hours=window_hours)

        # 1. Live Queue Metrics from local_queue_messages
        # pending: active, visible messages with attempts = 0 ready to be claimed
        # processing: claimed messages where visible_at > now
        # retrying: messages with attempts > 0 waiting for retry (not counted as pending)
        # dlq: messages in DLQ
        # oldest_pending_seconds: age of oldest pending message (or null)
        queue_stmt = text("""
            SELECT
                COUNT(*) FILTER (
                    WHERE queue_name = 'scraping-jobs'
                      AND status = 'pending'
                      AND attempts = 0
                      AND visible_at <= :now
                ) AS pending,
                COUNT(*) FILTER (
                    WHERE queue_name = 'scraping-jobs'
                      AND status = 'processing'
                      AND visible_at > :now
                ) AS processing,
                COUNT(*) FILTER (
                    WHERE queue_name = 'scraping-jobs'
                      AND status = 'pending'
                      AND attempts > 0
                ) AS retrying,
                COUNT(*) FILTER (
                    WHERE queue_name = 'scraping-jobs-dlq' OR status = 'dlq'
                ) AS dlq,
                MIN(created_at) FILTER (
                    WHERE queue_name = 'scraping-jobs'
                      AND status = 'pending'
                      AND attempts = 0
                      AND visible_at <= :now
                ) AS oldest_pending_at
            FROM local_queue_messages
        """)
        q_row = db.execute(queue_stmt, {"now": now_utc}).mappings().one()

        pending = int(q_row["pending"] or 0)
        processing = int(q_row["processing"] or 0)
        retrying = int(q_row["retrying"] or 0)
        dlq = int(q_row["dlq"] or 0)
        oldest_pending_at = q_row["oldest_pending_at"]

        oldest_pending_seconds: float | None = None
        if oldest_pending_at is not None:
            if oldest_pending_at.tzinfo is None:
                oldest_pending_at = oldest_pending_at.replace(tzinfo=timezone.utc)
            oldest_pending_seconds = round((now_utc - oldest_pending_at).total_seconds(), 2)

        # 2. Historical Jobs Metrics from scraping_jobs
        jobs_stmt = text("""
            SELECT
                COUNT(*) AS total_jobs,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed_jobs,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_jobs,
                COUNT(*) FILTER (WHERE status = 'dead_letter') AS dead_letter_jobs,
                COUNT(*) FILTER (WHERE status = 'skipped') AS skipped_jobs,
                COALESCE(SUM(observations_created), 0) AS total_observations,
                AVG(EXTRACT(EPOCH FROM (finished_at - started_at))) FILTER (
                    WHERE status = 'completed'
                      AND finished_at IS NOT NULL
                      AND started_at IS NOT NULL
                ) AS avg_duration
            FROM scraping_jobs
            WHERE created_at >= :window_start
        """)
        j_row = db.execute(jobs_stmt, {"window_start": window_start}).mappings().one()

        total_jobs = int(j_row["total_jobs"] or 0)
        completed_jobs = int(j_row["completed_jobs"] or 0)
        failed_jobs = int(j_row["failed_jobs"] or 0)
        dead_letter_jobs = int(j_row["dead_letter_jobs"] or 0)
        skipped_jobs = int(j_row["skipped_jobs"] or 0)
        total_obs = int(j_row["total_observations"] or 0)
        avg_dur = j_row["avg_duration"]

        success_rate: float | None = None
        if total_jobs > 0:
            success_rate = round((completed_jobs / total_jobs) * 100.0, 2)

        avg_duration_sec: float | None = None
        if avg_dur is not None:
            avg_duration_sec = round(float(avg_dur), 2)

        return ScrapingMetricsResponse(
            as_of=now_utc,
            pending=pending,
            processing=processing,
            retrying=retrying,
            dlq=dlq,
            oldest_pending_seconds=oldest_pending_seconds,
            window_hours=window_hours,
            total_jobs=total_jobs,
            completed_jobs=completed_jobs,
            failed_jobs=failed_jobs,
            dead_letter_jobs=dead_letter_jobs,
            skipped_jobs=skipped_jobs,
            success_rate_percentage=success_rate,
            average_duration_seconds=avg_duration_sec,
            total_observations_created=total_obs,
        )


dispatch_service = DispatchService()
