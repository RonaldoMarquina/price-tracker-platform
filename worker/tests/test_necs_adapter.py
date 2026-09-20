"""Tests for NecsAdapter using offline HTML fixtures and mocked HTTP transport."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.adapters.base import FatalScrapingError, TransientScrapingError
from app.adapters.necs_adapter import NecsAdapter
from app.core.network import SafeHttpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "necs"


def read_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def mock_client_with_html(html: str) -> SafeHttpClient:
    client = MagicMock(spec=SafeHttpClient)
    resp = MagicMock(spec=httpx.Response)
    resp.text = html
    resp.status_code = 200
    client.get.return_value = resp
    return client


def test_necs_product_in_stock():
    """Verify in-stock product extraction from JSON-LD and DOM."""
    html = read_fixture("product_in_stock.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://necs.pe/products/10744")

    assert res.price == Decimal("430.00")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "1414"
    assert res.mpn == "VY279HGR"
    assert "ASUS" in (res.name or "")
    assert res.image_url is not None


def test_necs_product_out_of_stock_with_price():
    """Verify out-of-stock product with published price is captured."""
    html = read_fixture("product_out_of_stock_with_price.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://necs.pe/products/15305")

    assert res.price == Decimal("290.00")
    assert res.currency == "PEN"
    assert res.availability == "out_of_stock"
    assert res.sku == "1588"
    assert res.mpn == "PRO H610M-A DDR4"


def test_necs_product_out_of_stock_without_price():
    """Verify out-of-stock product with no price sets price=None and currency=None."""
    html = read_fixture("product_out_of_stock_no_price.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://necs.pe/products/9999")

    assert res.price is None
    assert res.currency is None
    assert res.availability == "out_of_stock"
    assert res.sku == "9999"


def test_necs_product_malformed_jsonld_fallback():
    """Verify fallback to DOM when JSON-LD is syntactically invalid."""
    html = read_fixture("product_malformed_jsonld.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://necs.pe/products/keyboard")

    assert res.price == Decimal("150.00")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "KB-100"


def test_necs_product_missing_fields_raises_fatal():
    """Verify structure change / missing fields raises FatalScrapingError."""
    html = read_fixture("product_missing_fields.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="structure changed"):
        adapter.fetch_product_price("https://necs.pe/products/unknown")


def test_necs_zero_price_raises_fatal_when_in_stock():
    """Verify zero price for an in-stock product is rejected."""
    html = read_fixture("product_zero_price.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.fetch_product_price("https://necs.pe/products/zero")


def test_necs_negative_price_raises_fatal():
    """Verify negative price is rejected."""
    html = read_fixture("product_negative_price.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.fetch_product_price("https://necs.pe/products/negative")


def test_necs_unknown_currency_raises_fatal():
    """Verify unsupported currency (e.g. EUR) raises FatalScrapingError."""
    html = read_fixture("product_unknown_currency.html")
    adapter = NecsAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="Unsupported or unknown currency"):
        adapter.fetch_product_price("https://necs.pe/products/eur")


def test_necs_network_http_status_propagation():
    """Verify HTTP 404, 429, 500 and timeout propagate correctly from SafeHttpClient."""
    client = MagicMock(spec=SafeHttpClient)
    adapter = NecsAdapter(http_client=client)

    # 404
    client.get.side_effect = FatalScrapingError("Product page not found (HTTP 404)")
    with pytest.raises(FatalScrapingError, match="HTTP 404"):
        adapter.fetch_product_price("https://necs.pe/products/404")

    # 429
    client.get.side_effect = TransientScrapingError("Rate limit exceeded (HTTP 429)")
    with pytest.raises(TransientScrapingError, match="HTTP 429"):
        adapter.fetch_product_price("https://necs.pe/products/429")

    # 500
    client.get.side_effect = TransientScrapingError("Store server error (HTTP 500)")
    with pytest.raises(TransientScrapingError, match="HTTP 500"):
        adapter.fetch_product_price("https://necs.pe/products/500")

    # Timeout
    client.get.side_effect = TransientScrapingError("Connection timeout")
    with pytest.raises(TransientScrapingError, match="timeout"):
        adapter.fetch_product_price("https://necs.pe/products/timeout")
