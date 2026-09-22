"""Repository for persisting price observations with PostgreSQL ON CONFLICT DO NOTHING."""

import logging
import uuid
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import PriceObservation, Product, StoreProduct

logger = logging.getLogger("price-tracker.worker.repository")

STORE_IMAGE_DOMAIN_PRIORITY: dict[str, int] = {
    "cdn.memorykings.pe": 100,
    "memorykings.pe": 100,
    "www.memorykings.pe": 100,
    "necs.pe": 80,
    "www.necs.pe": 80,
    "computershopperu.com": 60,
    "www.computershopperu.com": 60,
    "cyccomputer.pe": 40,
    "www.cyccomputer.pe": 40,
}


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

    def update_store_product_image_url(
        self, db: Session, store_product_id: uuid.UUID, image_url: str | None
    ) -> bool:
        """Persist store product image URL non-destructively.

        Never overwrites an existing valid image URL with None or an empty string.
        """
        if not image_url or not image_url.strip():
            return False
        sp = db.get(StoreProduct, store_product_id)
        if not sp:
            return False
        clean_url = image_url.strip()
        if sp.image_url == clean_url:
            return False
        sp.image_url = clean_url
        db.commit()
        return True

    def update_product_canonical_image(
        self,
        db: Session,
        product_id: uuid.UUID,
        new_image_url: str | None,
        store_domain: str | None = None,
    ) -> bool:
        """Update canonical product image using a deterministic store priority rule.

        Priority order:
        1. Memory Kings (100)
        2. NECS (80)
        3. Computer Shop Perú (60)
        4. CyC Computer (40)

        Never replaces a valid image with None or empty string.
        If product has no image, any valid store image is assigned.
        If product already has an image, it is updated only if the current store
        has strictly higher priority than the existing image source domain.
        """
        if not new_image_url or not new_image_url.strip():
            return False
        product = db.get(Product, product_id)
        if not product:
            return False
        clean_url = new_image_url.strip()
        if not product.image_url:
            product.image_url = clean_url
            db.commit()
            return True

        # If already identical, nothing to do
        if product.image_url == clean_url:
            return False

        # Deterministic priority resolution if product already has image
        curr_host = ""
        try:
            curr_host = (urlparse(product.image_url).netloc or "").lower().split(":")[0]
        except Exception:
            curr_host = ""
        curr_priority = STORE_IMAGE_DOMAIN_PRIORITY.get(curr_host, 0)

        new_host = ""
        try:
            new_host = (urlparse(clean_url).netloc or "").lower().split(":")[0]
        except Exception:
            new_host = ""
        new_priority = max(
            STORE_IMAGE_DOMAIN_PRIORITY.get(new_host, 0),
            STORE_IMAGE_DOMAIN_PRIORITY.get(store_domain or "", 0),
        )

        if new_priority > curr_priority:
            product.image_url = clean_url
            db.commit()
            return True
        return False

    def insert_observation_idempotent(
        self,
        db: Session,
        store_product_id: uuid.UUID,
        price: Decimal | None,
        currency: str | None,
        availability: str | None,
        captured_at: datetime,
        source_hash: str,
        price_condition: str | None = None,
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
                price_condition=price_condition,
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
