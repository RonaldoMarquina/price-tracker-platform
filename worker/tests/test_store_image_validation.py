"""Tests for store image extraction, URL validation, and non-destructive persistence."""

import uuid
from unittest.mock import MagicMock

from app.adapters.base import validate_store_image_url
from app.adapters.computershop_adapter import (
    ALLOWED_COMPUTERSHOP_HOSTS,
    ComputerShopAdapter,
)
from app.adapters.cyc_adapter import ALLOWED_CYC_HOSTS, CycComputerAdapter
from app.adapters.memorykings_adapter import (
    ALLOWED_MEMORYKINGS_IMAGE_HOSTS,
    MemoryKingsAdapter,
)
from app.adapters.necs_adapter import ALLOWED_NECS_HOSTS, NecsAdapter
from app.db.models import Category, Product, Store, StoreProduct
from app.repositories.observation_repository import ObservationRepository


class TestValidateStoreImageUrl:
    """Test suite for validate_store_image_url helper."""

    def test_accepts_valid_https_url_on_allowed_domain(self):
        url = "https://cdn.memorykings.pe/files/2025/03/28/352612-MK039005-A.jpg"
        result = validate_store_image_url(url, ALLOWED_MEMORYKINGS_IMAGE_HOSTS)
        assert result == url

    def test_rejects_insecure_http(self):
        url = "http://necs.pe/15305-large_default/mainboard.jpg"
        result = validate_store_image_url(url, ALLOWED_NECS_HOSTS)
        assert result is None

    def test_rejects_unknown_domain(self):
        url = "https://unauthorized-cdn.com/images/gpu.png"
        result = validate_store_image_url(url, ALLOWED_NECS_HOSTS)
        assert result is None

    def test_rejects_common_placeholders(self):
        placeholders = [
            "https://computershopperu.com/img/no-image.png",
            "https://computershopperu.com/placeholder.jpg",
            "https://cyccomputer.pe/img/sin-imagen.png",
            "https://necs.pe/default-image.jpg",
            "https://cdn.memorykings.pe/product-default.png",
            "https://necs.pe/image-not-found.jpg",
        ]
        for ph in placeholders:
            assert (
                validate_store_image_url(
                    ph,
                    ALLOWED_COMPUTERSHOP_HOSTS
                    | ALLOWED_CYC_HOSTS
                    | ALLOWED_NECS_HOSTS
                    | ALLOWED_MEMORYKINGS_IMAGE_HOSTS,
                )
                is None
            )

    def test_rejects_non_string_and_empty(self):
        assert validate_store_image_url(None, ALLOWED_NECS_HOSTS) is None
        assert validate_store_image_url("", ALLOWED_NECS_HOSTS) is None
        assert validate_store_image_url("   ", ALLOWED_NECS_HOSTS) is None
        assert validate_store_image_url(12345, ALLOWED_NECS_HOSTS) is None


class TestAdapterImageExtraction:
    """Test offline image extraction across all 4 store adapters."""

    def test_necs_adapter_extracts_and_validates_image(self):
        html = """
        <html>
            <head>
                <meta property="og:image"
                      content="https://necs.pe/15305-large_default/mainboard.jpg" />
            </head>
            <body>
                <h1 class="product-title">MSI PRO H610M-A DDR4</h1>
                <span class="product-price">S/ 390.00</span>
                <span class="product-availability">Disponible</span>
            </body>
        </html>
        """
        adapter = NecsAdapter(http_client=MagicMock())
        result = adapter.parse_html(html, "https://necs.pe/products/15305")
        assert result.image_url == "https://necs.pe/15305-large_default/mainboard.jpg"

    def test_necs_adapter_rejects_insecure_or_placeholder_image(self):
        html = """
        <html>
            <head>
                <meta property="og:image" content="http://necs.pe/img/no-image.png" />
            </head>
            <body>
                <h1 class="product-title">MSI PRO H610M-A DDR4</h1>
                <span class="product-price">S/ 390.00</span>
            </body>
        </html>
        """
        adapter = NecsAdapter(http_client=MagicMock())
        result = adapter.parse_html(html, "https://necs.pe/products/15305")
        assert result.image_url is None

    def test_memorykings_adapter_extracts_cdn_image(self):
        html = """
        <html>
            <head>
                <meta property="og:image"
                      content="https://cdn.memorykings.pe/files/2025/03/28/352612.jpg" />
            </head>
            <body>
                <h1>Monitor ASUS VY279HGR</h1>
                <div class="price pt-1">S/ 480.00</div>
                <div class="stock">En stock</div>
            </body>
        </html>
        """
        adapter = MemoryKingsAdapter(http_client=MagicMock())
        result = adapter.parse_html(html, "https://www.memorykings.pe/producto/352612/monitor")
        assert result.image_url == "https://cdn.memorykings.pe/files/2025/03/28/352612.jpg"

    def test_computershop_adapter_extracts_valid_image(self):
        html = """
        <html>
            <head>
                <meta property="og:title"
                      content="DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)" />
                <meta property="og:image"
                      content="https://computershopperu.com/152912-thickbox_default/cooler.jpg" />
            </head>
            <body>
                <span class="product-price">S/ 320.00</span>
                <span id="product-availability">En stock</span>
            </body>
        </html>
        """
        adapter = ComputerShopAdapter(http_client=MagicMock())
        result = adapter.parse_html(html, "https://computershopperu.com/producto/40069-cooler.html")
        assert result.image_url == "https://computershopperu.com/152912-thickbox_default/cooler.jpg"

    def test_cyc_adapter_extracts_valid_image(self):
        html = """
        <html>
            <head>
                <meta property="og:title" content="Placa MSI PRO H610M-A (PN:911-7E31-002)" />
                <meta property="og:image" content="https://cyccomputer.pe/18398299/placa.jpg" />
            </head>
            <body>
                <span class="product-price">S/ 385.00</span>
                <span class="product-availability">Disponible</span>
            </body>
        </html>
        """
        adapter = CycComputerAdapter(http_client=MagicMock())
        result = adapter.parse_html(html, "https://cyccomputer.pe/producto/18398299-placa.html")
        assert result.image_url == "https://cyccomputer.pe/18398299/placa.jpg"


class TestNonDestructiveImagePersistence:
    """Test non-destructive persistence and deterministic canonical image priority."""

    def test_update_store_product_image_url_non_destructive(self):
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            repo = ObservationRepository()
            cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
            db.add(cat)
            db.flush()
            prod = Product(
                name="Test CPU", slug=f"test-cpu-{uuid.uuid4().hex[:6]}", category_id=cat.id
            )
            store = Store(
                name=f"Store-{uuid.uuid4().hex[:6]}", domain=f"store-{uuid.uuid4().hex[:6]}.pe"
            )
            db.add_all([prod, store])
            db.flush()

            sp = StoreProduct(
                product_id=prod.id,
                store_id=store.id,
                product_url="https://necs.pe/products/123",
                image_url=None,
            )
            db.add(sp)
            db.flush()

            # 1. First assign valid image
            valid_url = "https://necs.pe/123-large_default/cpu.jpg"
            updated = repo.update_store_product_image_url(db, sp.id, valid_url)
            assert updated is True
            db.refresh(sp)
            assert sp.image_url == valid_url

            # 2. Attempt to overwrite with None -> must be rejected
            assert repo.update_store_product_image_url(db, sp.id, None) is False
            db.refresh(sp)
            assert sp.image_url == valid_url

            # 3. Attempt to overwrite with empty string -> must be rejected
            assert repo.update_store_product_image_url(db, sp.id, "   ") is False
            db.refresh(sp)
            assert sp.image_url == valid_url
        finally:
            db.rollback()
            db.close()

    def test_update_product_canonical_image_deterministic_priority(self):
        from app.db.session import SessionLocal

        db = SessionLocal()
        try:
            repo = ObservationRepository()
            cat = Category(name=f"Cat-{uuid.uuid4().hex[:6]}", slug=f"cat-{uuid.uuid4().hex[:6]}")
            db.add(cat)
            db.flush()
            prod = Product(
                name="Test Monitor",
                slug=f"test-monitor-{uuid.uuid4().hex[:6]}",
                category_id=cat.id,
                image_url=None,
            )
            db.add(prod)
            db.flush()

            # 1. Product without image receives image from CyC (priority 40)
            cyc_img = "https://cyccomputer.pe/img/monitor.jpg"
            assert (
                repo.update_product_canonical_image(db, prod.id, cyc_img, "cyccomputer.pe") is True
            )
            db.refresh(prod)
            assert prod.image_url == cyc_img

            # 2. Higher priority from Computer Shop (60) replaces CyC (40)
            cs_img = "https://computershopperu.com/img/monitor.jpg"
            assert (
                repo.update_product_canonical_image(db, prod.id, cs_img, "computershopperu.com")
                is True
            )
            db.refresh(prod)
            assert prod.image_url == cs_img

            # 3. Higher priority from NECS (80) replaces Computer Shop (60)
            necs_img = "https://necs.pe/img/monitor.jpg"
            assert repo.update_product_canonical_image(db, prod.id, necs_img, "necs.pe") is True
            db.refresh(prod)
            assert prod.image_url == necs_img

            # 4. Highest priority from Memory Kings CDN (100) replaces NECS (80)
            mk_img = "https://cdn.memorykings.pe/files/monitor.jpg"
            assert (
                repo.update_product_canonical_image(db, prod.id, mk_img, "memorykings.pe") is True
            )
            db.refresh(prod)
            assert prod.image_url == mk_img

            # 5. Lower priority from CyC (40) CANNOT overwrite Memory Kings (100)
            assert (
                repo.update_product_canonical_image(db, prod.id, cyc_img, "cyccomputer.pe") is False
            )
            db.refresh(prod)
            assert prod.image_url == mk_img

            # 6. None or empty CANNOT overwrite valid canonical image
            assert repo.update_product_canonical_image(db, prod.id, None, "memorykings.pe") is False
            assert repo.update_product_canonical_image(db, prod.id, "", "memorykings.pe") is False
            db.refresh(prod)
            assert prod.image_url == mk_img
        finally:
            db.rollback()
            db.close()
