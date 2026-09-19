"""Product service containing business logic for catalog and price tracking."""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.exceptions import ProductNotFoundError
from app.repositories.product_repository import ProductRepository, product_repository
from app.schemas.price_history import (
    PricePointOut,
    ProductPriceHistoryResponse,
    StorePriceSeriesOut,
)
from app.schemas.product import (
    CategoryOut,
    LatestPriceOut,
    ProductDetailOut,
    ProductListItemOut,
    ProductListResponse,
    ProductStoreOut,
    StoreProductPriceOut,
)


class ProductService:
    """Business use cases for products and price historical data."""

    def __init__(self, repo: ProductRepository | None = None) -> None:
        self.repo = repo or product_repository

    def list_products(
        self,
        db: Session,
        q: str | None = None,
        category: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProductListResponse:
        """List active products with pagination, search, and category filter."""
        products, total = self.repo.get_paginated(
            db=db,
            q=q,
            category_slug=category,
            page=page,
            page_size=page_size,
        )

        items: list[ProductListItemOut] = []
        for prod in products:
            latest_price_tuple = self.repo.get_latest_price_for_product(db, prod.id)
            latest_price: LatestPriceOut | None = None
            if latest_price_tuple:
                price_amount, currency, store_name = latest_price_tuple
                latest_price = LatestPriceOut(
                    amount=f"{price_amount:.2f}",
                    currency=currency,
                    store=store_name,
                )

            items.append(
                ProductListItemOut(
                    id=prod.id,
                    name=prod.name,
                    brand=prod.brand,
                    category=prod.category.name,
                    image_url=prod.image_url,
                    latest_price=latest_price,
                )
            )

        return ProductListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
        )

    def get_product_detail(self, db: Session, product_id: uuid.UUID) -> ProductDetailOut:
        """Get product full detail with latest observed price per store."""
        product = self.repo.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))

        store_outs: list[ProductStoreOut] = []
        for sp in product.store_products:
            if not sp.is_active or not sp.store.is_active:
                continue

            latest_obs = self.repo.get_latest_price_for_store_product(db, sp.id)
            store_price_out: StoreProductPriceOut | None = None
            if latest_obs:
                store_price_out = StoreProductPriceOut(
                    amount=f"{latest_obs.price:.2f}",
                    currency=latest_obs.currency,
                    availability=latest_obs.availability,
                    captured_at=latest_obs.captured_at,
                )

            store_outs.append(
                ProductStoreOut(
                    store_id=sp.store.id,
                    store_name=sp.store.name,
                    product_url=sp.product_url,
                    external_sku=sp.external_sku,
                    latest_price=store_price_out,
                )
            )

        category_out = CategoryOut(
            id=product.category.id,
            name=product.category.name,
            slug=product.category.slug,
        )

        return ProductDetailOut(
            id=product.id,
            name=product.name,
            slug=product.slug,
            brand=product.brand,
            model=product.model,
            category=category_out,
            image_url=product.image_url,
            is_active=product.is_active,
            created_at=product.created_at,
            updated_at=product.updated_at,
            stores=store_outs,
        )

    def get_product_price_history(
        self,
        db: Session,
        product_id: uuid.UUID,
        store_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> ProductPriceHistoryResponse:
        """Get time-series of price observations grouped by store."""
        product = self.repo.get_by_id(db, product_id)
        if not product:
            raise ProductNotFoundError(str(product_id))

        store_products = self.repo.get_store_products(db, product_id, store_id=store_id)

        series_list: list[StorePriceSeriesOut] = []
        for sp in store_products:
            observations = self.repo.get_price_points_for_store_product(
                db=db,
                store_product_id=sp.id,
                date_from=date_from,
                date_to=date_to,
            )

            currency = observations[0].currency if observations else "PEN"
            points = [
                PricePointOut(
                    captured_at=obs.captured_at,
                    price=f"{obs.price:.2f}",
                )
                for obs in observations
            ]

            series_list.append(
                StorePriceSeriesOut(
                    store_id=sp.store.id,
                    store_name=sp.store.name,
                    currency=currency,
                    points=points,
                )
            )

        return ProductPriceHistoryResponse(
            product_id=product.id,
            series=series_list,
        )


product_service = ProductService()
