"""Minimal development seed data for Price Tracker Platform."""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("db.seed")


def seed_dev_data(db: Session) -> dict[str, int]:
    """Insert minimal development data idempotently without duplicates."""
    counts = {
        "categories": 0,
        "stores": 0,
        "products": 0,
        "store_products": 0,
        "price_observations": 0,
    }

    # 1. Categories
    categories_data = [
        {"name": "Procesadores", "slug": "procesadores"},
        {"name": "Tarjetas de Video", "slug": "tarjetas-de-video"},
        {"name": "Memorias RAM", "slug": "memorias-ram"},
    ]
    categories_map: dict[str, Category] = {}
    for cat_data in categories_data:
        existing = db.scalars(select(Category).where(Category.slug == cat_data["slug"])).first()
        if not existing:
            cat = Category(name=cat_data["name"], slug=cat_data["slug"])
            db.add(cat)
            db.flush()
            categories_map[cat.slug] = cat
            counts["categories"] += 1
        else:
            categories_map[existing.slug] = existing

    # 2. Stores
    stores_data = [
        {"name": "Impacto", "domain": "impacto.com.pe"},
        {"name": "Memory Kings", "domain": "memorykings.com.pe"},
    ]
    stores_map: dict[str, Store] = {}
    for store_data in stores_data:
        existing = db.scalars(select(Store).where(Store.domain == store_data["domain"])).first()
        if not existing:
            store = Store(name=store_data["name"], domain=store_data["domain"], is_active=True)
            db.add(store)
            db.flush()
            stores_map[store.domain] = store
            counts["stores"] += 1
        else:
            stores_map[existing.domain] = existing

    # 3. Products
    products_data = [
        {
            "name": "AMD Ryzen 7 5800X",
            "slug": "amd-ryzen-7-5800x",
            "category_slug": "procesadores",
            "brand": "AMD",
            "model": "5800X",
            "image_url": "https://example.com/images/ryzen-7-5800x.jpg",
        },
        {
            "name": "Intel Core i7-14700K",
            "slug": "intel-core-i7-14700k",
            "category_slug": "procesadores",
            "brand": "Intel",
            "model": "i7-14700K",
            "image_url": "https://example.com/images/i7-14700k.jpg",
        },
        {
            "name": "NVIDIA GeForce RTX 4070",
            "slug": "nvidia-geforce-rtx-4070",
            "category_slug": "tarjetas-de-video",
            "brand": "NVIDIA",
            "model": "RTX 4070",
            "image_url": "https://example.com/images/rtx-4070.jpg",
        },
    ]
    products_map: dict[str, Product] = {}
    for prod_data in products_data:
        existing = db.scalars(select(Product).where(Product.slug == prod_data["slug"])).first()
        if not existing:
            prod = Product(
                category_id=categories_map[prod_data["category_slug"]].id,
                name=prod_data["name"],
                slug=prod_data["slug"],
                brand=prod_data["brand"],
                model=prod_data["model"],
                image_url=prod_data["image_url"],
                is_active=True,
            )
            db.add(prod)
            db.flush()
            products_map[prod.slug] = prod
            counts["products"] += 1
        else:
            products_map[existing.slug] = existing

    # 4. Store Products
    store_products_data = [
        {
            "product_slug": "amd-ryzen-7-5800x",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/amd-ryzen-7-5800x",
            "external_sku": "SKU-RYZEN-5800X-IMP",
        },
        {
            "product_slug": "amd-ryzen-7-5800x",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/amd-ryzen-7-5800x",
            "external_sku": "MK-5800X-BOX",
        },
        {
            "product_slug": "nvidia-geforce-rtx-4070",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/geforce-rtx-4070",
            "external_sku": "SKU-RTX-4070-IMP",
        },
    ]
    store_products_map: dict[tuple[str, str], StoreProduct] = {}
    for sp_data in store_products_data:
        prod = products_map[sp_data["product_slug"]]
        store = stores_map[sp_data["store_domain"]]
        existing = db.scalars(
            select(StoreProduct).where(
                StoreProduct.product_id == prod.id,
                StoreProduct.store_id == store.id,
                StoreProduct.product_url == sp_data["product_url"],
            )
        ).first()
        if not existing:
            sp = StoreProduct(
                product_id=prod.id,
                store_id=store.id,
                product_url=sp_data["product_url"],
                external_sku=sp_data["external_sku"],
                is_active=True,
            )
            db.add(sp)
            db.flush()
            store_products_map[(sp_data["product_slug"], sp_data["store_domain"])] = sp
            counts["store_products"] += 1
        else:
            store_products_map[(sp_data["product_slug"], sp_data["store_domain"])] = existing

    # 5. Price Observations
    price_observations_data = [
        {
            "product_slug": "amd-ryzen-7-5800x",
            "store_domain": "impacto.com.pe",
            "price": Decimal("799.90"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60001",
            "captured_at": datetime(2026, 9, 18, 10, 0, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "amd-ryzen-7-5800x",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("820.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60002",
            "captured_at": datetime(2026, 9, 18, 10, 5, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "nvidia-geforce-rtx-4070",
            "store_domain": "impacto.com.pe",
            "price": Decimal("2450.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60003",
            "captured_at": datetime(2026, 9, 18, 10, 10, 0, tzinfo=timezone.utc),
        },
    ]
    for po_data in price_observations_data:
        sp = store_products_map[(po_data["product_slug"], po_data["store_domain"])]
        existing = db.scalars(
            select(PriceObservation).where(
                PriceObservation.store_product_id == sp.id,
                PriceObservation.source_hash == po_data["source_hash"],
            )
        ).first()
        if not existing:
            po = PriceObservation(
                store_product_id=sp.id,
                price=po_data["price"],
                currency=po_data["currency"],
                availability=po_data["availability"],
                source_hash=po_data["source_hash"],
                captured_at=po_data["captured_at"],
            )
            db.add(po)
            counts["price_observations"] += 1

    db.commit()
    logger.info("Seed completed. Created: %s", counts)
    return counts


def main() -> None:
    """CLI runner for seed data."""
    db = SessionLocal()
    try:
        seed_dev_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
