"""Repository for persisting price observations with PostgreSQL ON CONFLICT DO NOTHING."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import PriceObservation, StoreProduct

logger = logging.getLogger("price-tracker.worker.repository")


class ObservationRepository:
    """Repository handling store products and idempotent price observation persistence."""

    def get_store_product(
        self, db: Session, product_id: uuid.UUID, store_id: uuid.UUID
    ) -> StoreProduct | None:
        """Find active StoreProduct relationship for given product and store."""
        stmt = select(StoreProduct).where(
            StoreProduct.product_id == product_id,
            StoreProduct.store_id == store_id,
            StoreProduct.is_active.is_(True),
        )
        return db.execute(stmt).scalar_one_or_none()

    def insert_observation_idempotent(
        self,
        db: Session,
        store_product_id: uuid.UUID,
        price: Decimal,
        currency: str,
        availability: str | None,
        captured_at: datetime,
        source_hash: str,
    ) -> bool:
        """Insert observation with ON CONFLICT (source_hash) DO NOTHING for idempotency."""
        stmt = (
            insert(PriceObservation)
            .values(
                id=uuid.uuid4(),
                store_product_id=store_product_id,
                price=price,
                currency=currency,
                availability=availability,
                captured_at=captured_at,
                source_hash=source_hash,
            )
            .on_conflict_do_nothing(index_elements=["source_hash"])
        )
        result = db.execute(stmt)
        db.commit()
        inserted = bool(result.rowcount and result.rowcount > 0)
        if not inserted:
            logger.info(
                "IDEMPOTENT_SKIP: Observation already exists for source_hash=%s", source_hash
            )
        return inserted
