"""Service orchestrating scheduled and manual scraping dispatch, job listing, and queue metrics."""

import logging
import math
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from shared.adapters.store_capabilities import is_store_dispatchable
from shared.queue.base import BaseQueue
from shared.queue.models import LocalQueueMessage
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
from app.db.models import (
    Product,
    ScrapingDlqLedger,
    ScrapingJob,
    ScrapingOutbox,
    Store,
    StoreProduct,
)
from app.db.session import SessionLocal, engine
from app.schemas.scraping import (
    DLQMessageItemResponse,
    DLQMessageListResponse,
    DLQReplayResponse,
    ManualDispatchResponse,
    ScrapingJobDetailResponse,
    ScrapingJobListResponse,
    ScrapingMetricsResponse,
)

logger = logging.getLogger("price-tracker.dispatch")


def sanitize_error(msg: str | Exception | None, max_len: int = 500) -> str | None:
    """Sanitize and truncate error reason to avoid leaking sensitive internal traces."""
    if msg is None:
        return None
    text = str(msg).strip()
    # Remove Authorization headers / Bearer tokens
    text = re.sub(r"(?i)authorization:\s*(?:bearer\s+)?[^\s]+", "[REDACTED_AUTH]", text)
    text = re.sub(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "[REDACTED_TOKEN]", text)
    # Remove stack traces
    text = re.sub(
        r"(?i)traceback\s*\(most\s+recent\s+call\s+last\):.*",
        "[TRACEBACK_REDACTED]",
        text,
        flags=re.DOTALL,
    )
    lines = text.splitlines()
    cleaned = " ".join(line.strip() for line in lines if line.strip())
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned or None


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
                    db.execute(
                        select(Store).where(Store.is_active.is_(True)).order_by(Store.name.asc())
                    )
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

                        message = ScrapingMessage(
                            version=1,
                            job_id=job_id,
                            store_id=store.id,
                            product_ids=product_ids,
                            requested_at=job_created_at,
                            attempt=1,
                        )

                        job = ScrapingJob(
                            id=job_id,
                            store_id=store.id,
                            status="queued",
                            trigger_type="scheduled",
                            dispatch_slot=normalized_slot,
                            batch_size=len(product_ids),
                            observations_created=0,
                            attempts=0,
                            payload=message.model_dump(mode="json"),
                            created_at=job_created_at,
                        )
                        store_tx.add(job)

                        if os.getenv("QUEUE_BACKEND") == "sqs":
                            outbox_entry = ScrapingOutbox(
                                id=uuid.uuid4(),
                                aggregate_type="scraping_job",
                                aggregate_id=job_id,
                                event_type="initial_dispatch",
                                payload=message.model_dump(mode="json"),
                                status="pending",
                                attempts=0,
                                available_at=job_created_at,
                                idempotency_key=f"dispatch-{job_id}-1",
                                created_at=job_created_at,
                            )
                            store_tx.add(outbox_entry)
                        else:
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
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"La tienda '{target_store.name}' está desactivada.",
                        )

                    is_disp, reason = is_store_dispatchable(
                        target_store.domain, allow_offline=allow_offline_adapters
                    )
                    if not is_disp:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=(
                                f"La tienda '{target_store.name}' no tiene un adaptador "
                                f"habilitado ({reason})."
                            ),
                        )

                    candidate_stores = [target_store]
                else:
                    candidate_stores = (
                        db.execute(
                            select(Store)
                            .where(Store.is_active.is_(True))
                            .order_by(Store.name.asc())
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
                    logger.info("Store '%s' skipped in manual dispatch: %s", store.name, reason)
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

                        message = ScrapingMessage(
                            version=1,
                            job_id=job_id,
                            store_id=store.id,
                            product_ids=product_ids,
                            requested_at=job_created_at,
                            attempt=1,
                        )

                        job = ScrapingJob(
                            id=job_id,
                            store_id=store.id,
                            status="queued",
                            trigger_type="manual",
                            dispatch_slot=None,
                            batch_size=len(product_ids),
                            observations_created=0,
                            attempts=0,
                            payload=message.model_dump(mode="json"),
                            created_at=job_created_at,
                        )
                        store_tx.add(job)

                        if os.getenv("QUEUE_BACKEND") == "sqs":
                            outbox_entry = ScrapingOutbox(
                                id=uuid.uuid4(),
                                aggregate_type="scraping_job",
                                aggregate_id=job_id,
                                event_type="initial_dispatch",
                                payload=message.model_dump(mode="json"),
                                status="pending",
                                attempts=0,
                                available_at=job_created_at,
                                idempotency_key=f"dispatch-{job_id}-1",
                                created_at=job_created_at,
                            )
                            store_tx.add(outbox_entry)
                        else:
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
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="'from_date' cannot be later than 'to_date'.",
            )

        query = select(ScrapingJob, Store.name.label("store_name")).join(
            Store, ScrapingJob.store_id == Store.id
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

    def list_dlq_messages(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        store_id: uuid.UUID | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> DLQMessageListResponse:
        """List and inspect sanitized DLQ messages."""
        if from_date and to_date:
            if from_date.tzinfo is None:
                from_date = from_date.replace(tzinfo=timezone.utc)
            if to_date.tzinfo is None:
                to_date = to_date.replace(tzinfo=timezone.utc)
            if from_date > to_date:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Rango de fechas inválido: from_date debe ser menor o igual a to_date.",
                )

        if os.getenv("QUEUE_BACKEND") == "sqs":
            base_ledger_query = select(ScrapingDlqLedger).where(
                ScrapingDlqLedger.status.in_(["in_dlq", "replay_pending"])
            )
            if store_id:
                base_ledger_query = base_ledger_query.where(ScrapingDlqLedger.store_id == store_id)
            if from_date:
                base_ledger_query = base_ledger_query.where(
                    ScrapingDlqLedger.sent_to_dlq_at >= from_date
                )
            if to_date:
                base_ledger_query = base_ledger_query.where(
                    ScrapingDlqLedger.sent_to_dlq_at <= to_date
                )

            count_stmt = select(func.count()).select_from(base_ledger_query.subquery())
            total = db.execute(count_stmt).scalar_one()

            total_pages = math.ceil(total / page_size) if total > 0 else 0
            offset = (page - 1) * page_size

            data_stmt = (
                base_ledger_query.order_by(
                    ScrapingDlqLedger.sent_to_dlq_at.desc(), ScrapingDlqLedger.id.desc()
                )
                .offset(offset)
                .limit(page_size)
            )
            ledgers = db.execute(data_stmt).scalars().all()

            items: list[DLQMessageItemResponse] = []
            for entry in ledgers:
                replayable = True
                block_reason: str | None = None

                job = db.execute(
                    select(ScrapingJob).where(ScrapingJob.id == entry.job_id)
                ).scalar_one_or_none()

                if not job:
                    replayable = False
                    block_reason = "SCRAPING_JOB_NOT_FOUND"
                elif job.status != "dead_letter":
                    replayable = False
                    block_reason = f"JOB_STATUS_NOT_REPLAYABLE: {job.status}"
                elif entry.status != "in_dlq":
                    replayable = False
                    block_reason = f"LEDGER_STATUS_NOT_REPLAYABLE: {entry.status}"

                store_name: str | None = None
                if entry.store_id:
                    st = db.execute(
                        select(Store).where(Store.id == entry.store_id)
                    ).scalar_one_or_none()
                    if st:
                        store_name = st.name

                items.append(
                    DLQMessageItemResponse(
                        message_id=entry.id,
                        job_id=entry.job_id,
                        store_id=entry.store_id,
                        store_name=store_name,
                        products_count=entry.products_count,
                        attempts=entry.attempts,
                        error_reason=sanitize_error(entry.error_reason),
                        created_at=entry.created_at,
                        sent_to_dlq_at=entry.sent_to_dlq_at,
                        replay_count=entry.replay_count or 0,
                        replayed_at=entry.replayed_at,
                        replayable=replayable,
                        replay_block_reason=sanitize_error(block_reason),
                    )
                )

            return DLQMessageListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
            )

        effective_date = func.coalesce(
            LocalQueueMessage.sent_to_dlq_at,
            LocalQueueMessage.processed_at,
            LocalQueueMessage.created_at,
        )

        base_query = select(LocalQueueMessage).where(
            LocalQueueMessage.queue_name == "scraping-jobs-dlq",
            LocalQueueMessage.status == "dlq",
        )

        if store_id:
            base_query = base_query.where(
                LocalQueueMessage.payload["store_id"].astext == str(store_id)
            )

        if from_date:
            if from_date.tzinfo is None:
                from_date = from_date.replace(tzinfo=timezone.utc)
            base_query = base_query.where(effective_date >= from_date)

        if to_date:
            if to_date.tzinfo is None:
                to_date = to_date.replace(tzinfo=timezone.utc)
            base_query = base_query.where(effective_date <= to_date)

        count_stmt = select(func.count()).select_from(base_query.subquery())
        total = db.execute(count_stmt).scalar_one()

        total_pages = math.ceil(total / page_size) if total > 0 else 0
        offset = (page - 1) * page_size

        data_stmt = (
            base_query.order_by(effective_date.desc(), LocalQueueMessage.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        messages = db.execute(data_stmt).scalars().all()

        items: list[DLQMessageItemResponse] = []
        for msg in messages:
            payload = msg.payload
            job_uuid: uuid.UUID | None = None
            store_uuid: uuid.UUID | None = None
            products_count = 0
            replayable = True
            block_reason: str | None = None

            if not isinstance(payload, dict):
                replayable = False
                block_reason = "INVALID_DLQ_PAYLOAD: Not a JSON object"
            else:
                raw_job_id = payload.get("job_id")
                if raw_job_id:
                    try:
                        job_uuid = uuid.UUID(str(raw_job_id))
                    except ValueError:
                        job_uuid = None
                        replayable = False
                        block_reason = "INVALID_DLQ_PAYLOAD: Invalid job_id"
                else:
                    replayable = False
                    block_reason = "INVALID_DLQ_PAYLOAD: Missing job_id"

                raw_store_id = payload.get("store_id")
                if raw_store_id:
                    try:
                        store_uuid = uuid.UUID(str(raw_store_id))
                    except ValueError:
                        store_uuid = None
                        replayable = False
                        if not block_reason:
                            block_reason = "INVALID_DLQ_PAYLOAD: Invalid store_id"
                else:
                    replayable = False
                    if not block_reason:
                        block_reason = "INVALID_DLQ_PAYLOAD: Missing store_id"

                p_ids = payload.get("product_ids")
                if isinstance(p_ids, list):
                    products_count = len(p_ids)
                else:
                    replayable = False
                    if not block_reason:
                        block_reason = "INVALID_DLQ_PAYLOAD: Invalid or missing product_ids"

            store_name: str | None = None
            if store_uuid:
                st = db.execute(select(Store).where(Store.id == store_uuid)).scalar_one_or_none()
                if st:
                    store_name = st.name

            if replayable and job_uuid:
                job = db.execute(
                    select(ScrapingJob).where(ScrapingJob.id == job_uuid)
                ).scalar_one_or_none()
                if not job:
                    replayable = False
                    block_reason = "SCRAPING_JOB_NOT_FOUND"
                elif job.status != "dead_letter":
                    replayable = False
                    block_reason = f"JOB_STATUS_NOT_REPLAYABLE: {job.status}"

            sent_at = msg.sent_to_dlq_at or msg.processed_at or msg.created_at

            items.append(
                DLQMessageItemResponse(
                    message_id=msg.id,
                    job_id=job_uuid,
                    store_id=store_uuid,
                    store_name=store_name,
                    products_count=products_count,
                    attempts=msg.attempts,
                    error_reason=sanitize_error(msg.error_reason),
                    created_at=msg.created_at,
                    sent_to_dlq_at=sent_at,
                    replay_count=msg.replay_count or 0,
                    replayed_at=msg.replayed_at,
                    replayable=replayable,
                    replay_block_reason=sanitize_error(block_reason),
                )
            )

        return DLQMessageListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    def replay_dlq_messages(
        self,
        message_ids: list[uuid.UUID],
    ) -> DLQReplayResponse:
        """Atomically replay a batch of messages from DLQ back to active queue."""
        if not message_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="La lista de message_ids no puede estar vacía.",
            )
        if len(message_ids) > 50:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="No se pueden reproducir más de 50 mensajes por lote.",
            )
        if len(message_ids) != len(set(message_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="message_ids no puede contener identificadores duplicados.",
            )

        sorted_ids = sorted(message_ids)
        now_utc = datetime.now(timezone.utc)

        with self.session_factory() as db:
            try:
                ledger_count = db.execute(
                    select(func.count(ScrapingDlqLedger.id)).where(
                        ScrapingDlqLedger.id.in_(sorted_ids)
                    )
                ).scalar_one()

                if os.getenv("QUEUE_BACKEND") == "sqs" or ledger_count > 0:
                    stmt_ledgers = (
                        select(ScrapingDlqLedger)
                        .where(ScrapingDlqLedger.id.in_(sorted_ids))
                        .order_by(ScrapingDlqLedger.id.asc())
                        .with_for_update()
                    )
                    locked_ledgers = db.execute(stmt_ledgers).scalars().all()
                    found_ids = {entry.id for entry in locked_ledgers}
                    missing_ids = set(sorted_ids) - found_ids
                    if missing_ids:
                        raise HTTPException(
                            status_code=status.HTTP_404_NOT_FOUND,
                            detail=(
                                "Uno o más mensajes no existen: "
                                f"{[str(i) for i in sorted(missing_ids)]}"
                            ),
                        )

                    for entry in locked_ledgers:
                        if entry.status != "in_dlq":
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    f"El registro DLQ {entry.id} no se encuentra "
                                    f"en estado reproducible (actual: '{entry.status}', "
                                    "esperado: 'in_dlq')."
                                ),
                            )

                    # Lock associated ScrapingJobs
                    job_ids = sorted({entry.job_id for entry in locked_ledgers})
                    stmt_jobs = (
                        select(ScrapingJob)
                        .where(ScrapingJob.id.in_(job_ids))
                        .order_by(ScrapingJob.id.asc())
                        .with_for_update()
                    )
                    locked_jobs = {j.id: j for j in db.execute(stmt_jobs).scalars().all()}

                    replayed_msg_ids: list[uuid.UUID] = []
                    replayed_job_ids: list[uuid.UUID] = []

                    for entry in locked_ledgers:
                        job = locked_jobs.get(entry.job_id)
                        if not job:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    f"El ScrapingJob {entry.job_id} correspondiente "
                                    f"al registro DLQ {entry.id} no existe."
                                ),
                            )
                        if job.status != "dead_letter":
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=(
                                    f"El ScrapingJob {job.id} correspondiente al registro "
                                    f"DLQ {entry.id} no está en estado reproducible "
                                    f"(actual: '{job.status}', esperado: 'dead_letter')."
                                ),
                            )

                        new_logical_id = uuid.uuid4()
                        root_logical_id = entry.root_logical_message_id or entry.id
                        replayed_from_id = entry.id

                        # Extract product_ids from job.payload or StoreProduct
                        product_ids: list[uuid.UUID] = []
                        if isinstance(job.payload, dict) and "product_ids" in job.payload:
                            product_ids = [uuid.UUID(str(p)) for p in job.payload["product_ids"]]
                        else:
                            sp_rows = db.execute(
                                select(StoreProduct.product_id).where(
                                    StoreProduct.store_id == job.store_id,
                                    StoreProduct.is_active.is_(True),
                                )
                            ).scalars().all()
                            product_ids = list(sp_rows)

                        new_message = ScrapingMessage(
                            version=1,
                            job_id=job.id,
                            store_id=job.store_id,
                            product_ids=product_ids,
                            requested_at=now_utc,
                            attempt=1,
                            logical_message_id=new_logical_id,
                            root_logical_message_id=root_logical_id,
                            replayed_from_message_id=replayed_from_id,
                        )

                        # Update job
                        if job.error_reason:
                            job.last_dlq_reason = sanitize_error(job.error_reason)
                        job.status = "queued"
                        job.replay_count = (job.replay_count or 0) + 1
                        job.replayed_at = now_utc
                        job.attempts = 0
                        job.started_at = None
                        job.finished_at = None
                        job.error_reason = None
                        job.payload = new_message.model_dump(mode="json")

                        # Update ledger to replay_pending
                        entry.status = "replay_pending"
                        entry.replay_count = (entry.replay_count or 0) + 1
                        entry.replayed_at = now_utc

                        # Create outbox row
                        outbox_entry = ScrapingOutbox(
                            id=uuid.uuid4(),
                            aggregate_type="scraping_job",
                            aggregate_id=job.id,
                            event_type="replay",
                            source_ledger_id=entry.id,
                            payload=new_message.model_dump(mode="json"),
                            status="pending",
                            attempts=0,
                            available_at=now_utc,
                            idempotency_key=f"replay-{job.id}-{job.replay_count}",
                            created_at=now_utc,
                        )
                        db.add(outbox_entry)

                        replayed_msg_ids.append(entry.id)
                        if job.id not in replayed_job_ids:
                            replayed_job_ids.append(job.id)

                    db.commit()

                    logger.info(
                        "DLQ_REPLAY_SUCCESS (SQS Ledger): count=%d message_ids=%s job_ids=%s",
                        len(replayed_msg_ids),
                        [str(i) for i in replayed_msg_ids],
                        [str(i) for i in replayed_job_ids],
                    )

                    return DLQReplayResponse(
                        replayed_count=len(replayed_msg_ids),
                        message_ids=replayed_msg_ids,
                        job_ids=replayed_job_ids,
                        status="accepted",
                    )

                # 1. Lock messages in deterministic ascending SQL order
                stmt_msgs = (
                    select(LocalQueueMessage)
                    .where(LocalQueueMessage.id.in_(sorted_ids))
                    .order_by(LocalQueueMessage.id.asc())
                    .with_for_update()
                )
                locked_msgs = db.execute(stmt_msgs).scalars().all()

                found_ids = {m.id for m in locked_msgs}
                missing_ids = set(sorted_ids) - found_ids
                if missing_ids:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=(
                            "Uno o más mensajes no existen: "
                            f"{[str(i) for i in sorted(missing_ids)]}"
                        ),
                    )

                # Validate each message is in DLQ and has valid payload
                job_id_by_msg: dict[uuid.UUID, uuid.UUID] = {}
                for m in locked_msgs:
                    if m.queue_name != "scraping-jobs-dlq" or m.status != "dlq":
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"El mensaje {m.id} no se encuentra actualmente en la DLQ "
                                f"(queue='{m.queue_name}', status='{m.status}')."
                            ),
                        )

                    payload = m.payload
                    if not isinstance(payload, dict):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"El mensaje {m.id} tiene un payload malformado (no es dict).",
                        )

                    raw_job_id = payload.get("job_id")
                    if not raw_job_id:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"El mensaje {m.id} tiene un payload malformado (falta job_id).",
                        )
                    try:
                        job_uuid = uuid.UUID(str(raw_job_id))
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"El mensaje {m.id} tiene un job_id inválido en el payload.",
                        )

                    raw_store_id = payload.get("store_id")
                    if not raw_store_id:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"El mensaje {m.id} tiene un store_id ausente en el payload.",
                        )
                    try:
                        uuid.UUID(str(raw_store_id))
                    except ValueError:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"El mensaje {m.id} tiene un store_id inválido en el payload.",
                        )

                    p_ids = payload.get("product_ids")
                    if not isinstance(p_ids, list):
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"El mensaje {m.id} tiene product_ids ausente o inválido "
                                "en el payload."
                            ),
                        )

                    job_id_by_msg[m.id] = job_uuid

                # 2. Lock related ScrapingJobs in deterministic ascending SQL order
                sorted_job_ids = sorted(set(job_id_by_msg.values()))
                stmt_jobs = (
                    select(ScrapingJob)
                    .where(ScrapingJob.id.in_(sorted_job_ids))
                    .order_by(ScrapingJob.id.asc())
                    .with_for_update()
                )
                locked_jobs = {j.id: j for j in db.execute(stmt_jobs).scalars().all()}

                for msg_id, job_uuid in job_id_by_msg.items():
                    job = locked_jobs.get(job_uuid)
                    if not job:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"El ScrapingJob {job_uuid} correspondiente al mensaje {msg_id} "
                                "no existe."
                            ),
                        )
                    if job.status != "dead_letter":
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"El ScrapingJob {job_uuid} correspondiente al mensaje {msg_id} "
                                f"no está en estado reproducible (actual: '{job.status}', "
                                "esperado: 'dead_letter')."
                            ),
                        )

                # 3. Apply updates atomically
                replayed_msg_ids: list[uuid.UUID] = []
                replayed_job_ids: list[uuid.UUID] = []

                for m in locked_msgs:
                    job = locked_jobs[job_id_by_msg[m.id]]

                    # Move message back to active queue
                    m.queue_name = "scraping-jobs"
                    m.status = "pending"
                    m.attempts = 0
                    m.visible_at = now_utc
                    m.receipt_handle = None
                    m.replay_count = (m.replay_count or 0) + 1
                    m.replayed_at = now_utc

                    new_payload = dict(m.payload)
                    new_payload["attempt"] = 1
                    m.payload = new_payload

                    # Update ScrapingJob
                    if job.error_reason:
                        job.last_dlq_reason = sanitize_error(job.error_reason)
                    job.status = "queued"
                    job.replay_count = (job.replay_count or 0) + 1
                    job.replayed_at = now_utc
                    job.attempts = 0
                    job.started_at = None
                    job.finished_at = None
                    job.error_reason = None
                    # observations_created is preserved as cumulative total

                    replayed_msg_ids.append(m.id)
                    if job.id not in replayed_job_ids:
                        replayed_job_ids.append(job.id)

                db.commit()

                logger.info(
                    "DLQ_REPLAY_SUCCESS: count=%d message_ids=%s job_ids=%s",
                    len(replayed_msg_ids),
                    [str(i) for i in replayed_msg_ids],
                    [str(i) for i in replayed_job_ids],
                )

                return DLQReplayResponse(
                    replayed_count=len(replayed_msg_ids),
                    message_ids=replayed_msg_ids,
                    job_ids=replayed_job_ids,
                    status="accepted",
                )

            except Exception as exc:
                db.rollback()
                logger.error("DLQ replay transaction rolled back: %s", sanitize_error(str(exc)))
                raise


dispatch_service = DispatchService()
