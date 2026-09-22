"""Unit tests for CycComputerAdapter using offline HTML fixtures."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.base import FatalScrapingError, TransientScrapingError
from app.adapters.cyc_adapter import CycComputerAdapter
from app.core.network import SafeHttpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "cyc"


def read_fixture(filename: str) -> str:
    """Read HTML content from fixture file."""
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def test_cyc_product_in_stock():
    """Verify parsing a valid in-stock product with PEN price, MPN, SKU and image."""
    html = read_fixture("product_in_stock.html")
    adapter = CycComputerAdapter()
    url = (
        "https://cyccomputer.pe/producto/refrigeracion-aire/"
        "17390265-deepcool-ak620-digital-se-tira-led-argb-black.html"
    )

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("241.50")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"
    assert result.sku == "09022DCC001"
    assert result.raw_mpn == "R-AK620-BKADMN-GJD"
    assert result.comparison_mpn_key == "RAK620BKADMNGJD"
    assert "DEEPCOOL AK620" in (result.name or "")
    assert result.image_url == (
        "https://cyccomputer.pe/35210-large_default/deepcool-ak620-digital-se-tira-led-argb-black.jpg"
    )


def test_cyc_product_out_of_stock_with_price():
    """Verify parsing product explicitly out of stock with published price."""
    html = read_fixture("product_out_of_stock_with_price.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/socket-lga-1700-14va/18398299-msi-h610m.html"

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("269.10")
    assert result.currency == "PEN"
    assert result.availability == "out_of_stock"
    assert result.sku == "22054MS8082"
    assert result.raw_mpn == "911-7E31-002"
    assert result.comparison_mpn_key == "9117E31002"


def test_cyc_product_out_of_stock_without_price():
    """Verify parsing product out of stock without published price."""
    html = read_fixture("product_out_of_stock_without_price.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/cpu/5800x.html"

    result = adapter.parse_html(html, url)

    assert result.price is None
    assert result.currency is None
    assert result.availability == "out_of_stock"
    assert result.raw_mpn == "100-100000063WOF"
    assert result.comparison_mpn_key == "100100000063WOF"


def test_cyc_product_consult_availability_unknown():
    """Verify 'consultar disponibilidad' results in availability='unknown' and price=None."""
    html = read_fixture("product_consult_availability.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/memorias-usb/26549-kingston-exodia.html"

    result = adapter.parse_html(html, url)

    # PrestaShop template price S/ 1,031.55 must be rejected (price=None)
    assert result.price is None
    assert result.currency is None
    assert result.availability == "unknown"
    assert result.raw_mpn == "DTXM/64GB"
    assert result.comparison_mpn_key == "DTXM64GB"


def test_cyc_consult_availability_rejects_template_price_regression():
    """Regression test: ensure PrestaShop template price (S/ 1,031.55) is rejected.

    When status is 'Consultar disponibilidad', price must be None.
    """
    html = read_fixture("product_consult_availability.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/memorias-usb/26549-kingston-exodia.html"

    result = adapter.parse_html(html, url)

    assert result.price is None
    assert result.currency is None
    assert result.price != Decimal("1031.55")



def test_cyc_product_comma_thousands():
    """Verify parsing price with comma thousands separator: S/ 1,097.60."""
    html = read_fixture("product_comma_thousands.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/monitor/27.html"

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("1097.60")
    assert result.currency == "PEN"
    assert result.raw_mpn == "9S6-3CB51H-001"


def test_cyc_product_missing_pen_price_raises_fatal():
    """Verify page missing PEN currency raises FatalScrapingError."""
    html = read_fixture("product_missing_pen_price.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/cpu/12400.html"

    with pytest.raises(FatalScrapingError, match="No PEN price indicator found"):
        adapter.parse_html(html, url)


def test_cyc_product_missing_fields_raises_fatal():
    """Verify page missing mandatory fields raises FatalScrapingError."""
    html = read_fixture("product_missing_fields.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/error.html"

    with pytest.raises(FatalScrapingError, match="Missing required product fields"):
        adapter.parse_html(html, url)


def test_cyc_zero_price_raises_fatal_when_in_stock():
    """Verify zero price for in-stock item raises FatalScrapingError."""
    html = read_fixture("product_zero_price.html")
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/cable/hdmi.html"

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.parse_html(html, url)


def test_cyc_network_http_status_propagation():
    """Verify adapter propagates network errors correctly via SafeHttpClient."""
    mock_client = MagicMock(spec=SafeHttpClient)
    adapter = CycComputerAdapter(http_client=mock_client)
    url = "https://cyccomputer.pe/producto/item.html"

    mock_client.get.side_effect = FatalScrapingError("Not found 404")
    with pytest.raises(FatalScrapingError, match="Not found 404"):
        adapter.fetch_product_price(url)

    mock_client.get.side_effect = TransientScrapingError("Store server error (HTTP 503)")
    with pytest.raises(TransientScrapingError, match="503"):
        adapter.fetch_product_price(url)


def test_cyc_bundled_payment_methods_extracts_base_cash_price():
    """Verify that when cash and card surcharge prices appear, the base cash price is chosen."""
    html = """
    <html>
      <body>
        <h1>DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)</h1>
        <div class="product-prices">
          <div class="current-price">
            $ 70,00 (S/ 241,50) (impuestos inc.) *Sin recargo por pago en Efectivo o Transferencia
          </div>
          <div class="card-price">
            $ 73,50 (S/ 253,58) (impuestos inc.) *Con recargo de 5% adicional por pago con tarjeta
          </div>
        </div>
        <div class="product-reference">
          <span class="editable">09022DCC001</span>
        </div>
        <div class="product-availability">
          En stock 1 Artículos
        </div>
      </body>
    </html>
    """
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/ak620.html"

    result = adapter.parse_html(html, url)
    assert result.price == Decimal("241.50")
    assert result.price != Decimal("253.58")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"


def test_cyc_card_price_before_current_price_dom_order_resilience():
    """Verify that if card price appears ahead in DOM, base cash price is still chosen."""
    html = """
    <html>
      <body>
        <h1>DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)</h1>
        <div class="product-prices">
          <div class="card-price product-price">
            <span class="price">$ 73,50 (S/ 253,58)</span>
            <span>*Con recargo de 5% adicional por pago con tarjeta</span>
          </div>
          <div class="current-price">
            <span class="price product-price">$ 70,00 (S/ 241,50)</span>
            <span>*Sin recargo adicional por pago en Efectivo o Transferencia</span>
          </div>
        </div>
        <div class="product-reference">
          <span class="editable">09022DCC001</span>
        </div>
        <div class="product-availability">
          En stock 1 Artículos
        </div>
      </body>
    </html>
    """
    adapter = CycComputerAdapter()
    url = "https://cyccomputer.pe/producto/ak620.html"

    result = adapter.parse_html(html, url)
    assert result.price == Decimal("241.50")
    assert result.price != Decimal("253.58")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"
