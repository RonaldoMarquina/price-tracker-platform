"""Tests for SercoplusAdapter using offline HTML fixtures and mocked HTTP transport."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

from app.adapters.base import FatalScrapingError, TransientScrapingError
from app.adapters.sercoplus_adapter import SercoplusAdapter
from app.core.network import SafeHttpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sercoplus"


def read_fixture(filename: str) -> str:
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def mock_client_with_html(html: str) -> SafeHttpClient:
    client = MagicMock(spec=SafeHttpClient)
    resp = MagicMock(spec=httpx.Response)
    resp.text = html
    resp.status_code = 200
    client.get.return_value = resp
    return client


def test_sercoplus_product_in_stock_extracts_pen_only():
    """Verify in-stock product extracts PEN price published in DOM without mixing USD."""
    html = read_fixture("product_in_stock.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://sercoplus.com/monitores/asus-vy279hgr.html")

    assert res.price == Decimal("390.80")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "081040182"
    assert "ASUS" in (res.name or "")


def test_sercoplus_product_comma_decimal():
    """Verify Peruvian PrestaShop comma decimal format (e.g. S/ 862,34) parses correctly."""
    html = read_fixture("product_comma_decimal.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://sercoplus.com/cpu/intel-i5.html")

    assert res.price == Decimal("862.34")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "060112233"


def test_sercoplus_product_out_of_stock_with_price():
    """Verify out-of-stock product with published price is captured in PEN."""
    html = read_fixture("product_out_of_stock_with_price.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://sercoplus.com/socket-1700/msi-pro-h610m.html")

    assert res.price == Decimal("262.04")
    assert res.currency == "PEN"
    assert res.availability == "out_of_stock"
    assert res.sku == "060874167"


def test_sercoplus_product_out_of_stock_without_price():
    """Verify out-of-stock product without published price has price=None and currency=None."""
    html = read_fixture("product_out_of_stock_no_price.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://sercoplus.com/out-of-stock.html")

    assert res.price is None
    assert res.currency is None
    assert res.availability == "out_of_stock"


def test_sercoplus_product_malformed_jsonld_fallback():
    """Verify fallback to DOM when JSON-LD is invalid."""
    html = read_fixture("product_malformed_jsonld.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    res = adapter.fetch_product_price("https://sercoplus.com/mouse.html")

    assert res.price == Decimal("120.50")
    assert res.currency == "PEN"
    assert res.availability == "in_stock"
    assert res.sku == "050011223"


def test_sercoplus_product_missing_fields_raises_fatal():
    """Verify structure change / missing fields raises FatalScrapingError."""
    html = read_fixture("product_missing_fields.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="structure changed"):
        adapter.fetch_product_price("https://sercoplus.com/missing.html")


def test_sercoplus_zero_price_raises_fatal_when_in_stock():
    """Verify zero price for an in-stock product is rejected."""
    html = read_fixture("product_zero_price.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.fetch_product_price("https://sercoplus.com/zero.html")


def test_sercoplus_missing_pen_price_raises_fatal():
    """Verify page with no PEN price raises FatalScrapingError."""
    html = read_fixture("product_unknown_currency.html")
    adapter = SercoplusAdapter(http_client=mock_client_with_html(html))

    with pytest.raises(FatalScrapingError, match="missing published PEN price"):
        adapter.fetch_product_price("https://sercoplus.com/unknown-curr.html")


def test_sercoplus_network_http_status_propagation():
    """Verify HTTP 404, 429, 500 and timeout propagate correctly from SafeHttpClient."""
    client = MagicMock(spec=SafeHttpClient)
    adapter = SercoplusAdapter(http_client=client)

    # 404
    client.get.side_effect = FatalScrapingError("Product page not found (HTTP 404)")
    with pytest.raises(FatalScrapingError, match="HTTP 404"):
        adapter.fetch_product_price("https://sercoplus.com/404.html")

    # 429
    client.get.side_effect = TransientScrapingError("Rate limit exceeded (HTTP 429)")
    with pytest.raises(TransientScrapingError, match="HTTP 429"):
        adapter.fetch_product_price("https://sercoplus.com/429.html")

    # 500
    client.get.side_effect = TransientScrapingError("Store server error (HTTP 500)")
    with pytest.raises(TransientScrapingError, match="HTTP 500"):
        adapter.fetch_product_price("https://sercoplus.com/500.html")

    # Timeout
    client.get.side_effect = TransientScrapingError("Connection timeout")
    with pytest.raises(TransientScrapingError, match="timeout"):
        adapter.fetch_product_price("https://sercoplus.com/timeout.html")
