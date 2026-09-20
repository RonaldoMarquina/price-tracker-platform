"""Tests for MemoryKingsAdapter using offline HTML fixtures and mocked HTTP transport."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.adapters.base import FatalScrapingError, TransientScrapingError
from app.adapters.memorykings_adapter import MemoryKingsAdapter
from app.core.network import SafeHttpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "memorykings"


def read_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def mock_client_with_html(html: str) -> SafeHttpClient:
    client = MagicMock(spec=SafeHttpClient)
    resp = MagicMock(spec=httpx.Response)
    resp.text = html
    resp.status_code = 200
    client.get.return_value = resp
    return client


def test_mk_product_in_stock():
    """Verify in-stock product extraction from JSON-LD and URL SKU."""
    html = read_fixture("product_in_stock.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    url = "https://www.memorykings.pe/producto/352612/monitor-27-asus-vy279hgr-ips-fhd-120hz-1ms"
    res = adapter.fetch_product_price(url)

    assert res.price == Decimal("392.00")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "352612"
    assert res.mpn == "VY279HGR"
    assert "ASUS VY279HGR" in (res.name or "")
    assert res.image_url == "https://cdn.memorykings.pe/files/2025/03/28/352612-MK039005-A.jpg"


def test_mk_product_out_of_stock_with_price():
    """Verify out-of-stock product with published price is captured."""
    html = read_fixture("product_out_of_stock_with_price.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    url = "https://www.memorykings.pe/producto/352612/monitor-27-asus-vy279hgr-ips-fhd-120hz-1ms"
    res = adapter.fetch_product_price(url)

    assert res.price == Decimal("392.00")
    assert res.currency == "PEN"
    assert res.availability == "out_of_stock"
    assert res.sku == "352612"
    assert res.mpn == "VY279HGR"


def test_mk_product_out_of_stock_without_price():
    """Verify out-of-stock product with no price sets price=None and currency=None."""
    html = read_fixture("product_out_of_stock_without_price.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    url = "https://www.memorykings.pe/producto/352612/monitor-27-asus-vy279hgr-ips-fhd-120hz-1ms"
    res = adapter.fetch_product_price(url)

    assert res.price is None
    assert res.currency is None
    assert res.availability == "out_of_stock"
    assert res.sku == "352612"


def test_mk_product_malformed_jsonld_fallback():
    """Verify fallback to DOM when JSON-LD is syntactically invalid."""
    html = read_fixture("product_malformed_jsonld.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    url = "https://www.memorykings.pe/producto/352612/monitor-27-asus-vy279hgr-ips-fhd-120hz-1ms"
    res = adapter.fetch_product_price(url)

    assert res.price == Decimal("392.00")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "352612"


def test_mk_product_missing_fields_raises_fatal():
    """Verify structure change / missing fields raises FatalScrapingError."""
    html = read_fixture("product_missing_fields.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="structure changed"):
        adapter.fetch_product_price("https://www.memorykings.pe/producto/999999/desconocido")


def test_mk_unknown_currency_raises_fatal():
    """Verify non-PEN currency (e.g. EUR) raises FatalScrapingError."""
    html = read_fixture("product_unknown_currency.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="Unsupported currency"):
        adapter.fetch_product_price("https://www.memorykings.pe/producto/352612/eur")


def test_mk_invalid_price_raises_fatal():
    """Verify zero price for an in-stock product is rejected."""
    html = read_fixture("product_invalid_price.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.fetch_product_price("https://www.memorykings.pe/producto/352612/zero")


def test_mk_modified_structure():
    """Verify handling of nested JSON-LD @graph structure."""
    html = read_fixture("product_modified_structure.html")
    adapter = MemoryKingsAdapter(http_client=mock_client_with_html(html))

    url = "https://www.memorykings.pe/producto/353418/memoria-usb-128gb-kingston-dt-exodia-s"
    res = adapter.fetch_product_price(url)

    assert res.price == Decimal("40.50")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.mpn == "DTXS/128GB"
    assert res.sku == "353418"


def test_mk_network_http_status_propagation():
    """Verify network exceptions bubble up as expected."""
    client = MagicMock(spec=SafeHttpClient)
    client.get.side_effect = TransientScrapingError("Rate limit exceeded")
    adapter = MemoryKingsAdapter(http_client=client)

    with pytest.raises(TransientScrapingError, match="Rate limit exceeded"):
        adapter.fetch_product_price("https://www.memorykings.pe/producto/352612/rate-limit")
