"""Scraping orchestration service for worker."""

import hashlib
import logging

from shared.schemas.scraping import ScrapingMessage
from sqlalchemy.orm import Session

from app.adapters.base import (
    BaseStoreAdapter,
    FatalScrapingError,
    StoreDisabledError,
)
from app.adapters.registry import AdapterRegistry, default_registry
from app.db.models import Store
from app.repositories.observation_repository import ObservationRepository

logger = logging.getLogger("price-tracker.worker.scraping")


class ScrapingWorkerService:
    """Orchestrates scraping execution and idempotent persistence."""

    def __init__(
        self,
        adapter: BaseStoreAdapter | None = None,
        repository: ObservationRepository | None = None,
        registry: AdapterRegistry | None = None,
    ) -> None:
        self.adapter = adapter
        self.repository = repository or ObservationRepository()
        self.registry = registry

    def process_job(self, db: Session, message: ScrapingMessage) -> int:
        """Process all product extractions in a scraping job message."""
        # 1. Validate Store existence and active state
        store = db.get(Store, message.store_id)
        if not store:
            if not self.adapter:
                raise FatalScrapingError(
                    f"Store with id '{message.store_id}' not found in database"
                )
        elif not store.is_active:
            raise StoreDisabledError(
                f"Store '{store.name}' ({store.domain}) is deactivated; skipping job"
            )

        # 2. Resolve adapter
        if self.adapter:
            adapter = self.adapter
        else:
            if not store:
                raise FatalScrapingError(
                    f"Store with id '{message.store_id}' not found in database"
                )
            reg = self.registry or default_registry
            adapter = reg.get_adapter(store.domain)

        inserted_count = 0

        for product_id in message.product_ids:
            store_product = self.repository.get_store_product(
                db=db,
                product_id=product_id,
                store_id=message.store_id,
            )

            if not store_product:
                logger.warning(
                    "StoreProduct not found for product_id=%s store_id=%s. Skipping item.",
                    str(product_id),
                    str(message.store_id),
                )
                continue

            # Deterministic source hash calculated from job_id and store_product_id
            idempotency_key = f"{message.job_id}:{store_product.id}"
            source_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()

            # Execute store adapter (can throw TransientScrapingError or FatalScrapingError)
            scraped = adapter.fetch_product_price(store_product.product_url)

            # Persist observation with ON CONFLICT (source_hash) DO NOTHING
            was_inserted = self.repository.insert_observation_idempotent(
                db=db,
                store_product_id=store_product.id,
                price=scraped.price,
                currency=scraped.currency,
                availability=scraped.availability,
                captured_at=scraped.captured_at,
                source_hash=source_hash,
            )

            if was_inserted:
                inserted_count += 1

        return inserted_count
