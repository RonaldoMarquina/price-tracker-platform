"""Idempotent seed data for development and testing environments."""

import logging
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def seed_dev_data(db: Session) -> dict[str, int]:
    """Insert initial hardware components data idempotently."""
    counts = {
        "categories": 0,
        "stores": 0,
        "products": 0,
        "store_products": 0,
        "price_observations": 0,
    }

    # 1. Categories - Exactly the 6 core PC hardware categories requested
    categories_data = [
        {"name": "Procesadores", "slug": "procesadores"},
        {"name": "Tarjetas de Video", "slug": "tarjetas-de-video"},
        {"name": "Memorias RAM", "slug": "memorias-ram"},
        {"name": "Placas Madre", "slug": "placas-madre"},
        {"name": "Fuentes de Poder", "slug": "fuentes-de-poder"},
        {"name": "Refrigeración", "slug": "refrigeracion"},
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

    # 3. Products across all 6 core categories
    products_data = [
        # Procesadores
        {
            "name": "AMD Ryzen 7 5800X",
            "slug": "amd-ryzen-7-5800x",
            "category_slug": "procesadores",
            "brand": "AMD",
            "model": "5800X",
            "image_url": "https://images.unsplash.com/photo-1591799264318-7e6ef8ddb7ea?w=400",
        },
        {
            "name": "Intel Core i7-14700K",
            "slug": "intel-core-i7-14700k",
            "category_slug": "procesadores",
            "brand": "Intel",
            "model": "i7-14700K",
            "image_url": "https://images.unsplash.com/photo-1555618568-963d30b1b11b?w=400",
        },
        # Tarjetas de Video
        {
            "name": "NVIDIA GeForce RTX 4070",
            "slug": "nvidia-geforce-rtx-4070",
            "category_slug": "tarjetas-de-video",
            "brand": "NVIDIA",
            "model": "RTX 4070",
            "image_url": "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=400",
        },
        # Memorias RAM
        {
            "name": "Kingston Fury Beast DDR5 32GB (2x16GB) 6000MHz",
            "slug": "kingston-fury-beast-ddr5-32gb",
            "category_slug": "memorias-ram",
            "brand": "Kingston",
            "model": "KF560C36BBEK2-32",
            "image_url": "https://images.unsplash.com/photo-1562976540-1502c2145186?w=400",
        },
        {
            "name": "Corsair Vengeance LPX DDR4 16GB (2x8GB) 3200MHz",
            "slug": "corsair-vengeance-lpx-ddr4-16gb",
            "category_slug": "memorias-ram",
            "brand": "Corsair",
            "model": "CMK16GX4M2B3200C16",
            "image_url": "https://images.unsplash.com/photo-1562976540-1502c2145186?w=400",
        },
        # Placas Madre
        {
            "name": "ASUS ROG Strix B650-A Gaming WiFi",
            "slug": "asus-rog-strix-b650-a-gaming-wifi",
            "category_slug": "placas-madre",
            "brand": "ASUS",
            "model": "ROG-STRIX-B650-A",
            "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400",
        },
        {
            "name": "MSI MAG B760 Tomahawk WiFi",
            "slug": "msi-mag-b760-tomahawk-wifi",
            "category_slug": "placas-madre",
            "brand": "MSI",
            "model": "MAG-B760-TOMAHAWK",
            "image_url": "https://images.unsplash.com/photo-1518770660439-4636190af475?w=400",
        },
        # Fuentes de Poder
        {
            "name": "Corsair RM850e 850W 80 Plus Gold Modular",
            "slug": "corsair-rm850e-850w-80-plus-gold",
            "category_slug": "fuentes-de-poder",
            "brand": "Corsair",
            "model": "CP-9020263-NA",
            "image_url": "https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=400",
        },
        # Refrigeración (Líquida y Aire)
        {
            "name": "NZXT Kraken 240 RGB Refrigeración Líquida",
            "slug": "nzxt-kraken-240-rgb-refrigeracion-liquida",
            "category_slug": "refrigeracion",
            "brand": "NZXT",
            "model": "RL-KR240-B1",
            "image_url": "https://images.unsplash.com/photo-1591799264318-7e6ef8ddb7ea?w=400",
        },
        {
            "name": "DeepCool AK620 Refrigeración por Aire",
            "slug": "deepcool-ak620-refrigeracion-por-aire",
            "category_slug": "refrigeracion",
            "brand": "DeepCool",
            "model": "R-AK620-BKNNMT-G",
            "image_url": "https://images.unsplash.com/photo-1591799264318-7e6ef8ddb7ea?w=400",
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
            "product_slug": "intel-core-i7-14700k",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/intel-core-i7-14700k",
            "external_sku": "SKU-I7-14700K-IMP",
        },
        {
            "product_slug": "nvidia-geforce-rtx-4070",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/geforce-rtx-4070",
            "external_sku": "SKU-RTX-4070-IMP",
        },
        {
            "product_slug": "nvidia-geforce-rtx-4070",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/nvidia-geforce-rtx-4070",
            "external_sku": "MK-RTX-4070-12G",
        },
        {
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/kingston-fury-ddr5-32gb",
            "external_sku": "SKU-KF560C36BBEK2-32",
        },
        {
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/kingston-fury-beast-ddr5-32gb",
            "external_sku": "MK-DDR5-32GB-FURY",
        },
        {
            "product_slug": "corsair-vengeance-lpx-ddr4-16gb",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/corsair-vengeance-ddr4-16gb",
            "external_sku": "MK-CORSAIR-16GB-LPX",
        },
        {
            "product_slug": "asus-rog-strix-b650-a-gaming-wifi",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/asus-rog-strix-b650-a",
            "external_sku": "SKU-ROG-B650-A",
        },
        {
            "product_slug": "msi-mag-b760-tomahawk-wifi",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/msi-mag-b760-tomahawk",
            "external_sku": "MK-MSI-B760-TOM",
        },
        {
            "product_slug": "corsair-rm850e-850w-80-plus-gold",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/corsair-rm850e-850w",
            "external_sku": "SKU-RM850E-GOLD",
        },
        {
            "product_slug": "nzxt-kraken-240-rgb-refrigeracion-liquida",
            "store_domain": "memorykings.com.pe",
            "product_url": "https://www.memorykings.com.pe/producto/nzxt-kraken-240-rgb",
            "external_sku": "MK-NZXT-KRAKEN-240",
        },
        {
            "product_slug": "deepcool-ak620-refrigeracion-por-aire",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/deepcool-ak620",
            "external_sku": "SKU-DEEPCOOL-AK620",
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
            "product_slug": "intel-core-i7-14700k",
            "store_domain": "impacto.com.pe",
            "price": Decimal("1720.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60010",
            "captured_at": datetime(2026, 9, 18, 10, 8, 0, tzinfo=timezone.utc),
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
        {
            "product_slug": "nvidia-geforce-rtx-4070",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("2499.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60011",
            "captured_at": datetime(2026, 9, 18, 10, 12, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "impacto.com.pe",
            "price": Decimal("489.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60004",
            "captured_at": datetime(2026, 9, 18, 10, 15, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("510.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60012",
            "captured_at": datetime(2026, 9, 18, 10, 18, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "corsair-vengeance-lpx-ddr4-16gb",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("185.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60005",
            "captured_at": datetime(2026, 9, 18, 10, 20, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "asus-rog-strix-b650-a-gaming-wifi",
            "store_domain": "impacto.com.pe",
            "price": Decimal("1050.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60006",
            "captured_at": datetime(2026, 9, 18, 10, 25, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "msi-mag-b760-tomahawk-wifi",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("890.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60007",
            "captured_at": datetime(2026, 9, 18, 10, 30, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "corsair-rm850e-850w-80-plus-gold",
            "store_domain": "impacto.com.pe",
            "price": Decimal("560.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60008",
            "captured_at": datetime(2026, 9, 18, 10, 35, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "nzxt-kraken-240-rgb-refrigeracion-liquida",
            "store_domain": "memorykings.com.pe",
            "price": Decimal("620.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60009",
            "captured_at": datetime(2026, 9, 18, 10, 40, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "deepcool-ak620-refrigeracion-por-aire",
            "store_domain": "impacto.com.pe",
            "price": Decimal("280.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60013",
            "captured_at": datetime(2026, 9, 18, 10, 45, 0, tzinfo=timezone.utc),
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
