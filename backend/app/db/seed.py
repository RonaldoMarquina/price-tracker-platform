"""Idempotent seed data for development and testing environments."""

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Category, PriceObservation, Product, Store, StoreProduct
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def seed_canonical_catalog(
    db: Session,
) -> tuple[dict[str, int], dict[tuple[str, str], StoreProduct]]:
    """Insert initial canonical hardware catalog idempotently without fake observations."""
    counts = {
        "categories": 0,
        "stores": 0,
        "products": 0,
        "store_products": 0,
        "price_observations": 0,
    }


    # 1. Categories - Core PC hardware categories
    categories_data = [
        {"name": "Procesadores", "slug": "procesadores"},
        {"name": "Tarjetas de Video", "slug": "tarjetas-de-video"},
        {"name": "Memorias RAM", "slug": "memorias-ram"},
        {"name": "Placas Madre", "slug": "placas-madre"},
        {"name": "Fuentes de Poder", "slug": "fuentes-de-poder"},
        {"name": "Refrigeración", "slug": "refrigeracion"},
        {"name": "Monitores", "slug": "monitores"},
        {"name": "Almacenamiento", "slug": "almacenamiento"},
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
        {"name": "Impacto", "domain": "impacto.com.pe", "is_active": False},
        {"name": "Memory Kings", "domain": "memorykings.pe", "is_active": True},
        {"name": "NECS Ayacucho", "domain": "necs.pe", "is_active": True},
        {"name": "Computer Shop Perú", "domain": "computershopperu.com", "is_active": True},
        {"name": "CyC Computer", "domain": "cyccomputer.pe", "is_active": True},
        # Sercoplus is kept offline-only / deactivated due to Cloudflare bot challenge
        {"name": "Sercoplus", "domain": "sercoplus.com", "is_active": False},
    ]
    stores_map: dict[str, Store] = {}
    for store_data in stores_data:
        existing = db.scalars(
            select(Store).where(
                (Store.domain == store_data["domain"]) | (Store.name == store_data["name"])
            )
        ).first()
        is_active = store_data.get("is_active", True)
        if not existing:
            store = Store(name=store_data["name"], domain=store_data["domain"], is_active=is_active)
            db.add(store)
            db.flush()
            stores_map[store.domain] = store
            counts["stores"] += 1
        else:
            existing.domain = store_data["domain"]
            existing.is_active = is_active
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
            "mpn": "90MB1BP0-M0EAY0",
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
            "mpn": "R-AK620-BKNNMT-G",
            "image_url": "https://images.unsplash.com/photo-1591799264318-7e6ef8ddb7ea?w=400",
        },
        {
            "name": 'Monitor ASUS VY279HGR 27" IPS FHD 120Hz',
            "slug": "asus-vy279hgr-27-ips",
            "category_slug": "monitores",
            "brand": "ASUS",
            "model": "VY279HGR",
            "mpn": "VY279HGR",
            "image_url": "https://cdn.memorykings.pe/files/2025/03/28/352612-MK039005-A.jpg",
        },
        {
            "name": "Memoria USB Kingston DataTraveler Exodia S 128GB",
            "slug": "kingston-datatraveler-exodia-s-128gb",
            "category_slug": "almacenamiento",
            "brand": "Kingston",
            "model": "DataTraveler Exodia S",
            "mpn": "DTXS/128GB",
            "image_url": "https://cdn.memorykings.pe/files/2025/03/28/353418-MK039010.jpg",
        },
        {
            "name": "Multigrabador Externo DVD LG GP65NB60 Slim",
            "slug": "lg-gp65nb60-slim-dvd",
            "category_slug": "almacenamiento",
            "brand": "LG",
            "model": "GP65NB60",
            "mpn": "GP65NB60",
            "image_url": "https://cdn.memorykings.pe/files/2024/09/20/093353-A.jpg",
        },
        {
            "name": "Mainboard MSI PRO H610M-A DDR4",
            "slug": "msi-pro-h610m-a-ddr4",
            "category_slug": "placas-madre",
            "brand": "MSI",
            "model": "PRO H610M-A DDR4",
            "mpn": "PRO H610M-A DDR4",
            "image_url": "https://necs.pe/15305-large_default/mainboard-msi-pro-h610m-a-ddr4-lga-1700.jpg",
        },
        {
            "name": "DeepCool AK620 Digital SE ARGB Black",
            "slug": "deepcool-ak620-digital-se-argb-black",
            "category_slug": "refrigeracion",
            "brand": "DeepCool",
            "model": "AK620 Digital SE",
            "mpn": "R-AK620-BKADMN-GJD",
            "image_url": "https://computershopperu.com/152912-thickbox_default/deepcool-ak620-digital-se-black-argb-cooler-cpu-refrigeracion-aire-compatible-amdintel-pnr-ak620-bkadmn-gjd.jpg",
        },
        {
            "name": "Memoria USB Kingston DataTraveler Exodia M 64GB",
            "slug": "kingston-datatraveler-exodia-m-64gb",
            "category_slug": "almacenamiento",
            "brand": "Kingston",
            "model": "DataTraveler Exodia M",
            "mpn": "DTXM/64GB",
            "image_url": "https://necs.pe/7901-large_default/memoria-usb-kingston-64gb-datatraveler-exodia-m-usb-32-azul-negro.jpg",
        },
        {
            "name": "Memoria RAM Kingston Fury Beast RGB DDR5 32GB 5200MHz",
            "slug": "kingston-fury-beast-rgb-ddr5-32gb-5200mhz",
            "category_slug": "memorias-ram",
            "brand": "Kingston",
            "model": "Fury Beast RGB DDR5",
            "mpn": "KF552C40BBA-32",
            "image_url": "https://computershopperu.com/131062-thickbox_default/memoria-32gb-ddr5-kingston-fury-beast-rgb-black-bus-5200mhz-pnkf552c40bba-32.jpg",
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
                mpn=prod_data.get("mpn"),
                image_url=prod_data["image_url"],
                is_active=True,
            )
            db.add(prod)
            db.flush()
            products_map[prod.slug] = prod
            counts["products"] += 1
        else:
            if not existing.mpn and prod_data.get("mpn"):
                existing.mpn = prod_data["mpn"]
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
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/kingston-fury-ddr5-32gb",
            "external_sku": "SKU-KF560C36BBEK2-32",
        },
        {
            "product_slug": "asus-rog-strix-b650-a-gaming-wifi",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/asus-rog-strix-b650-a",
            "external_sku": "SKU-ROG-B650-A",
        },
        {
            "product_slug": "corsair-rm850e-850w-80-plus-gold",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/corsair-rm850e-850w",
            "external_sku": "SKU-RM850E-GOLD",
        },
        {
            "product_slug": "deepcool-ak620-refrigeracion-por-aire",
            "store_domain": "impacto.com.pe",
            "product_url": "https://www.impacto.com.pe/producto/deepcool-ak620",
            "external_sku": "SKU-DEEPCOOL-AK620",
        },
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "necs.pe",
            "product_url": "https://necs.pe/products/15305",
            "external_sku": "1588",
        },
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "sercoplus.com",
            "product_url": "https://sercoplus.com/socket-1700/643503-mainboard-msi-pro-h610m-a-ddr4-lga-1700.html",
            "external_sku": "060874167",
        },
        {
            "product_slug": "asus-vy279hgr-27-ips",
            "store_domain": "necs.pe",
            "product_url": "https://necs.pe/products/10744",
            "external_sku": "1414",
        },
        {
            "product_slug": "asus-vy279hgr-27-ips",
            "store_domain": "sercoplus.com",
            "product_url": "https://sercoplus.com/monitores-25-28/643846-monitor-asus-vy279hgr-27-ips-fhd-120.html",
            "external_sku": "081040182",
        },
        {
            "product_slug": "asus-vy279hgr-27-ips",
            "store_domain": "memorykings.pe",
            "product_url": "https://www.memorykings.pe/producto/352612/monitor-27-asus-vy279hgr-ips-fhd-120hz-1ms",
            "external_sku": "352612",
        },
        {
            "product_slug": "kingston-datatraveler-exodia-s-128gb",
            "store_domain": "necs.pe",
            "product_url": "https://necs.pe/products/7351",
            "external_sku": "1191",
        },
        {
            "product_slug": "kingston-datatraveler-exodia-s-128gb",
            "store_domain": "memorykings.pe",
            "product_url": "https://www.memorykings.pe/producto/353418/memoria-usb-128gb-kingston-dt-exodia-s",
            "external_sku": "353418",
        },
        {
            "product_slug": "lg-gp65nb60-slim-dvd",
            "store_domain": "necs.pe",
            "product_url": "https://necs.pe/products/142",
            "external_sku": "0143",
        },
        {
            "product_slug": "lg-gp65nb60-slim-dvd",
            "store_domain": "memorykings.pe",
            "product_url": "https://www.memorykings.pe/producto/93353/grabador-dvd-usb-super-multi-lg-gp65nb60-slim",
            "external_sku": "93353",
        },
        {
            "product_slug": "asus-rog-strix-b650-a-gaming-wifi",
            "store_domain": "computershopperu.com",
            "product_url": "https://computershopperu.com/producto/placa-socket-amd-am5/23146-placa-asus-rog-strix-b650-a-gaming-wifi-atx-ddr5-amd-am5-pn90mb1bp0-m0eay0.html",
            "external_sku": "114026001",
        },
        {
            "product_slug": "deepcool-ak620-digital-se-argb-black",
            "store_domain": "computershopperu.com",
            "product_url": "https://computershopperu.com/producto/refrigeracion-aire/40069-deepcool-ak620-digital-se-black-argb-cooler-cpu-refrigeracion-aire-compatible-amdintel-pnr-ak620-bkadmn-gjd.html",
            "external_sku": "269645564",
        },
        {
            "product_slug": "kingston-datatraveler-exodia-m-64gb",
            "store_domain": "necs.pe",
            "product_url": "https://necs.pe/products/3849",
            "external_sku": "0869",
        },
        {
            "product_slug": "kingston-datatraveler-exodia-m-64gb",
            "store_domain": "computershopperu.com",
            "product_url": "https://computershopperu.com/producto/memoria-usb/29942-memoria-usb-64gb-kingston-datatraveler-exodia-m-azul-version-32-pnkc-u2l64-7lb.html",
            "external_sku": "302900002",
        },
        # Disabled due to commercial price anomaly (KF552C40BBA-32 published
        # at $499 USD / S/ 1,711.57) pending verification before activation.
        {
            "product_slug": "kingston-fury-beast-rgb-ddr5-32gb-5200mhz",
            "store_domain": "computershopperu.com",
            "product_url": "https://computershopperu.com/producto/memoria-ram-ddr5-pc/24247-memoria-32gb-ddr5-kingston-fury-beast-rgb-black-bus-5200mhz-pnkf552c40bba-32.html",
            "external_sku": "271129008",
            "is_active": False,
        },
        {
            "product_slug": "deepcool-ak620-digital-se-argb-black",
            "store_domain": "cyccomputer.pe",
            "product_url": "https://cyccomputer.pe/producto/refrigeracion-aire/17390265-deepcool-ak620-digital-se-tira-led-argb-black-refrigeracion-aire-amdintel-pnr-ak620-bkadmn-gjd.html",
            "external_sku": "09022DCC001",
        },
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "cyccomputer.pe",
            "product_url": "https://cyccomputer.pe/producto/socket-lga-1700-14va/18398299-placa-msi-pro-h610m-a-ddr4-lga-1700-pn911-7e31-002-.html",
            "external_sku": "22054MS8082",
        },
        {
            "product_slug": "kingston-datatraveler-exodia-m-64gb",
            "store_domain": "cyccomputer.pe",
            "product_url": "https://cyccomputer.pe/producto/memorias-usb/26549-memoria-usb-64gb-kingston-data-traveler-exodia-m-blue-black-v-32-pndtxm64gb.html",
            "external_sku": "16066KG0205",
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
        is_active = sp_data.get("is_active", True)
        if not existing:
            sp = StoreProduct(
                product_id=prod.id,
                store_id=store.id,
                product_url=sp_data["product_url"],
                external_sku=sp_data["external_sku"],
                is_active=is_active,
            )
            db.add(sp)
            db.flush()
            store_products_map[(sp_data["product_slug"], sp_data["store_domain"])] = sp
            counts["store_products"] += 1
        else:
            if existing.external_sku != sp_data["external_sku"]:
                existing.external_sku = sp_data["external_sku"]
            if existing.is_active != is_active:
                existing.is_active = is_active
            store_products_map[(sp_data["product_slug"], sp_data["store_domain"])] = existing

    return counts, store_products_map


def seed_demo_observations(
    db: Session, store_products_map: dict[tuple[str, str], StoreProduct]
) -> int:
    """Insert demonstrative price observations for local visual testing only.

    Must ONLY be executed when SEED_DEMO_OBSERVATIONS=true is explicitly set.
    """
    demo_count = 0
    # 5. Demonstrative Price Observations (Visual fixtures only)
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
            "product_slug": "kingston-fury-beast-ddr5-32gb",
            "store_domain": "impacto.com.pe",
            "price": Decimal("489.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60004",
            "captured_at": datetime(2026, 9, 18, 10, 15, 0, tzinfo=timezone.utc),
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
            "product_slug": "corsair-rm850e-850w-80-plus-gold",
            "store_domain": "impacto.com.pe",
            "price": Decimal("560.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60008",
            "captured_at": datetime(2026, 9, 18, 10, 35, 0, tzinfo=timezone.utc),
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
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "necs.pe",
            "price": Decimal("290.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "a1b2c3d4e5f60030",
            "captured_at": datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "sercoplus.com",
            "price": Decimal("262.04"),
            "currency": "PEN",
            "availability": "out_of_stock",
            "source_hash": "a1b2c3d4e5f60031",
            "captured_at": datetime(2026, 9, 19, 12, 5, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "asus-vy279hgr-27-ips",
            "store_domain": "necs.pe",
            "price": Decimal("430.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "necs-obs-vy279hgr-01",
            "captured_at": datetime(2026, 9, 19, 12, 10, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "asus-vy279hgr-27-ips",
            "store_domain": "memorykings.pe",
            "price": Decimal("392.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "mk-obs-vy279hgr-01",
            "captured_at": datetime(2026, 9, 19, 12, 15, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-datatraveler-exodia-s-128gb",
            "store_domain": "necs.pe",
            "price": Decimal("45.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "necs-obs-exodia-01",
            "captured_at": datetime(2026, 9, 19, 12, 20, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-datatraveler-exodia-s-128gb",
            "store_domain": "memorykings.pe",
            "price": Decimal("40.50"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "mk-obs-exodia-01",
            "captured_at": datetime(2026, 9, 19, 12, 25, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "lg-gp65nb60-slim-dvd",
            "store_domain": "necs.pe",
            "price": Decimal("115.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "necs-obs-gp65-01",
            "captured_at": datetime(2026, 9, 19, 12, 30, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "lg-gp65nb60-slim-dvd",
            "store_domain": "memorykings.pe",
            "price": Decimal("102.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "mk-obs-gp65-01",
            "captured_at": datetime(2026, 9, 19, 12, 35, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "asus-rog-strix-b650-a-gaming-wifi",
            "store_domain": "computershopperu.com",
            "price": Decimal("1097.60"),
            "currency": "PEN",
            "availability": "out_of_stock",
            "source_hash": "cs-obs-rog-b650a-01",
            "captured_at": datetime(2026, 9, 20, 0, 0, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "deepcool-ak620-digital-se-argb-black",
            "store_domain": "computershopperu.com",
            "price": Decimal("253.13"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "cs-obs-ak620-dig-01",
            "captured_at": datetime(2026, 9, 20, 0, 5, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-datatraveler-exodia-m-64gb",
            "store_domain": "necs.pe",
            "price": Decimal("38.00"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "necs-obs-exodia-m64-01",
            "captured_at": datetime(2026, 9, 20, 0, 10, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-datatraveler-exodia-m-64gb",
            "store_domain": "computershopperu.com",
            "price": Decimal("30.84"),
            "currency": "PEN",
            "availability": "out_of_stock",
            "source_hash": "cs-obs-exodia-m64-01",
            "captured_at": datetime(2026, 9, 20, 0, 15, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "kingston-fury-beast-rgb-ddr5-32gb-5200mhz",
            "store_domain": "computershopperu.com",
            "price": Decimal("1711.57"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "cs-obs-fury-32gb-01",
            "captured_at": datetime(2026, 9, 20, 0, 20, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "deepcool-ak620-digital-se-argb-black",
            "store_domain": "cyccomputer.pe",
            "price": Decimal("241.50"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "cyc-obs-ak620-dig-01",
            "captured_at": datetime(2026, 9, 20, 1, 0, 0, tzinfo=timezone.utc),
        },
        {
            "product_slug": "msi-pro-h610m-a-ddr4",
            "store_domain": "cyccomputer.pe",
            "price": Decimal("269.10"),
            "currency": "PEN",
            "availability": "in_stock",
            "source_hash": "cyc-obs-h610m-01",
            "captured_at": datetime(2026, 9, 20, 1, 5, 0, tzinfo=timezone.utc),
        },
    ]
    for po_data in price_observations_data:
        sp = store_products_map[(po_data["product_slug"], po_data["store_domain"])]
        store_domain = po_data["store_domain"]
        condition = (
            "cash_or_bank_transfer"
            if store_domain in ("computershopperu.com", "cyccomputer.pe")
            else "standard"
        )
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
                price_condition=condition,
                source_hash=po_data["source_hash"],
                captured_at=po_data["captured_at"],
            )
            db.add(po)
            demo_count += 1
        else:
            existing.price = po_data["price"]
            existing.currency = po_data["currency"]
            existing.availability = po_data["availability"]
            existing.price_condition = condition

    return demo_count


def seed_dev_data(
    db: Session, include_demo_observations: bool | None = None
) -> dict[str, int]:
    """Seed database idempotently.

    By default (SEED_DEMO_OBSERVATIONS=false or unset):
    - Seeds the canonical catalog (categories, stores, products, store_products).
    - Seeds ZERO mock price observations.

    When include_demo_observations=True (or env SEED_DEMO_OBSERVATIONS=true):
    - Additionally inserts demonstrative visual observations.
    """
    if include_demo_observations is None:
        include_demo_observations = (
            os.getenv("SEED_DEMO_OBSERVATIONS", "false").strip().lower() in ("true", "1", "yes")
        )

    counts, store_products_map = seed_canonical_catalog(db)

    if include_demo_observations:
        logger.info("SEED_DEMO_OBSERVATIONS=true: inserting demonstrative observations.")
        demo_count = seed_demo_observations(db, store_products_map)
        counts["price_observations"] = demo_count
    else:
        logger.info("Default seed mode: inserting canonical catalog only (zero fake observations).")

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
