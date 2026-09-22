"""Tests for catalog seed data integrity, idempotency, and security constraints."""

import ast
import inspect

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import PriceObservation, Product, Store, StoreProduct
from app.db.seed import seed_canonical_catalog, seed_dev_data

ALLOWED_STORE_DOMAINS = {
    "impacto.com.pe",
    "memorykings.pe",
    "necs.pe",
    "computershopperu.com",
    "cyccomputer.pe",
    "sercoplus.com",
}


def test_seed_static_invariants():
    """Verify static invariants of canonical catalog definitions before DB insertion."""
    from app.db import seed

    source = inspect.getsource(seed)
    assert "memorykings.com.pe" not in source, "Forbidden memorykings.com.pe in seed.py"
    assert "MK-" not in source, "Forbidden MK-* SKU prefix in seed.py"

    mod = ast.parse(source)
    products_data_ast = None
    store_products_data_ast = None

    for node in ast.walk(mod):
        if isinstance(node, ast.FunctionDef) and node.name == "seed_canonical_catalog":
            for sub in node.body:
                if isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        if isinstance(target, ast.Name) and target.id == "products_data":
                            products_data_ast = sub.value
                        elif isinstance(target, ast.Name) and target.id == "store_products_data":
                            store_products_data_ast = sub.value

    assert products_data_ast is not None, "Missing products_data in seed"
    assert store_products_data_ast is not None, "Missing store_products_data in seed"

    # Assert exactly 17 canonical products and 24 store products defined
    assert len(products_data_ast.elts) == 17
    assert len(store_products_data_ast.elts) == 24

    # Check store products data
    sp_entries = []
    for elt in store_products_data_ast.elts:
        entry = {k.value: v.value for k, v in zip(elt.keys, elt.values)}
        sp_entries.append(entry)

    for sp in sp_entries:
        assert sp["store_domain"] in ALLOWED_STORE_DOMAINS
        assert not sp.get("external_sku", "").startswith("MK-")
        assert "memorykings.com.pe" not in sp["product_url"]
        assert sp["store_domain"] in sp["product_url"]

    # Verify exact updated SKUs in data definitions
    target_slug = "kingston-datatraveler-exodia-m-64gb"
    necs_entry = next(
        sp for sp in sp_entries
        if sp["store_domain"] == "necs.pe" and sp["product_slug"] == target_slug
    )
    assert necs_entry["external_sku"] == "0869"

    cyc_entry = next(
        sp for sp in sp_entries
        if sp["store_domain"] == "cyccomputer.pe" and sp["product_slug"] == target_slug
    )
    assert cyc_entry["external_sku"] == "16066KG0205"

    # Verify anomalous RAM is explicitly defined as is_active=False
    ram_slug = "kingston-fury-beast-rgb-ddr5-32gb-5200mhz"
    cs_ram = next(
        sp for sp in sp_entries
        if sp["store_domain"] == "computershopperu.com" and sp["product_slug"] == ram_slug
    )
    assert cs_ram.get("is_active") is False
    assert cs_ram.get("external_sku") == "271129008"


def test_seed_default_creates_canonical_catalog_with_zero_fake_observations(db_session: Session):
    """Verify default seed ensures 17 products, 24 store_products, and 0 fake observations."""
    counts, sp_map = seed_canonical_catalog(db_session)
    assert len(sp_map) == 24

    # Default seed_dev_data creates zero fake observations
    dev_counts = seed_dev_data(db_session, include_demo_observations=False)
    assert dev_counts.get("price_observations", 0) == 0

    # Verify all 24 canonical store products in database
    for _key, sp in sp_map.items():
        assert sp.store.domain in ALLOWED_STORE_DOMAINS
        assert sp.store.domain in sp.product_url
        assert not (sp.external_sku or "").startswith("MK-")
        assert "memorykings.com.pe" not in sp.product_url

        obs_count = db_session.scalar(
            select(func.count(PriceObservation.id)).where(
                PriceObservation.store_product_id == sp.id
            )
        )
        assert obs_count is not None

    # Verify exact updated SKUs in database
    necs_exodia = db_session.scalar(
        select(StoreProduct)
        .join(Store, StoreProduct.store_id == Store.id)
        .join(Product, StoreProduct.product_id == Product.id)
        .where(
            Store.domain == "necs.pe",
            Product.slug == "kingston-datatraveler-exodia-m-64gb",
        )
    )
    assert necs_exodia is not None
    assert necs_exodia.external_sku == "0869"

    cyc_exodia = db_session.scalar(
        select(StoreProduct)
        .join(Store, StoreProduct.store_id == Store.id)
        .join(Product, StoreProduct.product_id == Product.id)
        .where(
            Store.domain == "cyccomputer.pe",
            Product.slug == "kingston-datatraveler-exodia-m-64gb",
        )
    )
    assert cyc_exodia is not None
    assert cyc_exodia.external_sku == "16066KG0205"


def test_seed_idempotence(db_session: Session):
    """Verify executing seed repeatedly does not duplicate records or create side effects."""
    # Ensure canonical catalog is seeded
    seed_canonical_catalog(db_session)

    # Calling seed_dev_data again must insert 0 new canonical items
    second_counts = seed_dev_data(db_session, include_demo_observations=False)
    assert second_counts["categories"] == 0
    assert second_counts["stores"] == 0
    assert second_counts["products"] == 0
    assert second_counts["store_products"] == 0
    assert second_counts["price_observations"] == 0

    # Calling a third time continues to be idempotent
    third_counts = seed_dev_data(db_session, include_demo_observations=False)
    assert third_counts["categories"] == 0
    assert third_counts["stores"] == 0
    assert third_counts["products"] == 0
    assert third_counts["store_products"] == 0
    assert third_counts["price_observations"] == 0


def test_anomalous_ram_association_deactivated_and_excluded_from_dispatch(db_session: Session):
    """Verify anomalous RAM is deactivated, stays inactive, and is excluded from dispatch."""
    # 1. Execute seed first time
    _counts, sp_map = seed_canonical_catalog(db_session)
    assert len(sp_map) == 24

    # Query Computer Shop RAM StoreProduct
    ram_slug = "kingston-fury-beast-rgb-ddr5-32gb-5200mhz"
    cs_ram_sp = db_session.scalar(
        select(StoreProduct)
        .join(Store, StoreProduct.store_id == Store.id)
        .join(Product, StoreProduct.product_id == Product.id)
        .where(
            Store.domain == "computershopperu.com",
            Product.slug == ram_slug,
        )
    )
    assert cs_ram_sp is not None
    assert cs_ram_sp.is_active is False
    assert cs_ram_sp.external_sku == "271129008"
    assert cs_ram_sp.product.mpn == "KF552C40BBA-32"

    # 2. Execute seed second time (idempotence must not reactivate it)
    seed_canonical_catalog(db_session)
    db_session.refresh(cs_ram_sp)
    assert cs_ram_sp.is_active is False

    # 3. Verify other canonical Computer Shop associations remain active
    canonical_cs_slugs = {
        "asus-rog-strix-b650-a-gaming-wifi",
        "deepcool-ak620-digital-se-argb-black",
        "kingston-datatraveler-exodia-m-64gb",
    }
    cs_other_sps = db_session.scalars(
        select(StoreProduct)
        .join(Store, StoreProduct.store_id == Store.id)
        .join(Product, StoreProduct.product_id == Product.id)
        .where(
            Store.domain == "computershopperu.com",
            Product.slug.in_(canonical_cs_slugs),
        )
    ).all()
    assert len(cs_other_sps) == 3
    for sp in cs_other_sps:
        assert sp.is_active is True

    # 4. Verify dispatcher selection logic strictly excludes the anomalous RAM
    cs_store = db_session.scalar(
        select(Store).where(Store.domain == "computershopperu.com")
    )
    assert cs_store is not None

    dispatchable_product_ids = set(
        db_session.scalars(
            select(StoreProduct.product_id)
            .join(Product, StoreProduct.product_id == Product.id)
            .where(
                StoreProduct.store_id == cs_store.id,
                StoreProduct.is_active.is_(True),
                Product.is_active.is_(True),
            )
        ).all()
    )

    # Must contain the active canonical products, but NEVER the anomalous RAM
    assert cs_ram_sp.product_id not in dispatchable_product_ids
    for sp in cs_other_sps:
        assert sp.product_id in dispatchable_product_ids

    # 5. Global invariants: zero MK-* SKUs, zero MK URLs across all canonical products
    for (_prod_slug, _domain), sp in sp_map.items():
        assert not (sp.external_sku or "").startswith("MK-")
        assert "memorykings.com.pe" not in sp.product_url
