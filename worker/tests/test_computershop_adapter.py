"""Unit tests for ComputerShopAdapter using offline HTML fixtures."""

from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.adapters.base import FatalScrapingError, TransientScrapingError
from app.adapters.computershop_adapter import ComputerShopAdapter
from app.core.network import SafeHttpClient

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "computershop"


def read_fixture(filename: str) -> str:
    """Read HTML content from fixture file."""
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8")


def test_computershop_product_in_stock():
    """Verify parsing a valid in-stock product with PEN price, MPN, SKU and image."""
    html = read_fixture("product_in_stock.html")
    adapter = ComputerShopAdapter()
    url = (
        "https://computershopperu.com/producto/refrigeracion-aire/"
        "40069-deepcool-ak620-digital-se-black-argb-cooler-cpu-pnr-ak620-bkadmn-gjd.html"
    )

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("253.13")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"
    assert result.sku == "269645564"
    assert result.raw_mpn == "R-AK620-BKADMN-GJD"
    assert result.comparison_mpn_key == "RAK620BKADMNGJD"
    assert "DEEPCOOL AK620" in (result.name or "")
    assert result.image_url == (
        "https://computershopperu.com/11065-large_default/deepcool-ak620-digital-se-black-argb.jpg"
    )


def test_computershop_product_out_of_stock_with_price():
    """Verify parsing product explicitly out of stock with published price."""
    html = read_fixture("product_out_of_stock_with_price.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/placa/23146-asus-b650.html"

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("1097.60")
    assert result.currency == "PEN"
    assert result.availability == "out_of_stock"
    assert result.sku == "114026001"
    assert result.raw_mpn == "90MB1BP0'M0EAY0"
    assert result.comparison_mpn_key == "90MB1BP0M0EAY0"


def test_computershop_product_out_of_stock_without_price():
    """Verify parsing product out of stock without published price."""
    html = read_fixture("product_out_of_stock_without_price.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/cpu/5800x.html"

    result = adapter.parse_html(html, url)

    assert result.price is None
    assert result.currency is None
    assert result.availability == "out_of_stock"
    assert result.raw_mpn == "100-100000063WOF"
    assert result.comparison_mpn_key == "100100000063WOF"


def test_computershop_product_consult_availability_unknown():
    """Verify 'consultar disponibilidad' results in availability='unknown'."""
    html = read_fixture("product_consult_availability.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/case/pa602.html"

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("995.00")
    assert result.currency == "PEN"
    assert result.availability == "unknown"
    assert result.raw_mpn == "90DC00J0-B08010"
    assert result.comparison_mpn_key == "90DC00J0B08010"


def test_computershop_product_apostrophe_raw_mpn_integrity():
    """Verify adapter preserves apostrophe in raw_mpn without converting to hyphen."""
    html = read_fixture("product_apostrophe_mpn.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/placa/b650a.html"

    result = adapter.parse_html(html, url)

    # raw_mpn must keep the exact single quote as published
    assert result.raw_mpn == "90MB1BP0'M0EAY0"
    # comparison key must strip non-alphanumeric chars
    assert result.comparison_mpn_key == "90MB1BP0M0EAY0"


def test_computershop_product_comma_thousands():
    """Verify parsing price with comma thousands separator: S/ 1,097.60."""
    html = read_fixture("product_comma_thousands.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/monitor/274qpf.html"

    result = adapter.parse_html(html, url)

    assert result.price == Decimal("1097.60")
    assert result.currency == "PEN"
    assert result.raw_mpn == "9S6-3CB51H-001"


def test_computershop_product_missing_pen_price_raises_fatal():
    """Verify page missing PEN currency raises FatalScrapingError."""
    html = read_fixture("product_missing_pen_price.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/cpu/12400.html"

    with pytest.raises(FatalScrapingError, match="No PEN price indicator found"):
        adapter.parse_html(html, url)


def test_computershop_product_missing_fields_raises_fatal():
    """Verify page missing mandatory fields raises FatalScrapingError."""
    html = read_fixture("product_missing_fields.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/error.html"

    with pytest.raises(FatalScrapingError, match="Missing required product fields"):
        adapter.parse_html(html, url)


def test_computershop_zero_price_raises_fatal_when_in_stock():
    """Verify zero price for in-stock item raises FatalScrapingError."""
    html = read_fixture("product_zero_price.html")
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/cable/hdmi.html"

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        adapter.parse_html(html, url)


def test_computershop_network_http_status_propagation():
    """Verify adapter propagates network errors correctly via SafeHttpClient."""
    mock_client = MagicMock(spec=SafeHttpClient)
    adapter = ComputerShopAdapter(http_client=mock_client)
    url = "https://computershopperu.com/producto/item.html"

    mock_client.get.side_effect = FatalScrapingError("Not found 404")
    with pytest.raises(FatalScrapingError, match="Not found 404"):
        adapter.fetch_product_price(url)

    mock_client.get.side_effect = TransientScrapingError("Store server error (HTTP 503)")
    with pytest.raises(TransientScrapingError, match="503"):
        adapter.fetch_product_price(url)


def test_computershop_bundled_payment_methods_extracts_cash_price():
    """Verify that when cash and card surcharge prices appear, the base cash price is chosen."""
    html = """
    <html>
      <body>
        <h1>DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)</h1>
        <div class="product-prices">
          <div class="current-price">
            $ 73,80 (S/ 253,13) (impuestos inc.) *Sin recargo adicional por pago en Efectivo
          </div>
          <div class="card-price">
            $ 77,49 (S/ 265,79) (impuestos inc.) *Con recargo de 5% adicional por pago con tarjeta
          </div>
        </div>
        <div class="product-reference">
          <span class="editable">269645564</span>
        </div>
        <div class="product-availability">
          En stock 4 Artículos
        </div>
      </body>
    </html>
    """
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/ak620.html"

    result = adapter.parse_html(html, url)
    # S/ 253.13 is the selected base_price (condition: cash_or_bank_transfer)
    assert result.price == Decimal("253.13")
    # S/ 265.79 is ignored and never stored as price
    assert result.price != Decimal("265.79")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"


def test_computershop_card_price_before_current_price_dom_order_resilience():
    """Verify that if card price appears ahead in DOM, base cash price is still chosen."""
    html = """
    <html>
      <body>
        <h1>DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)</h1>
        <div class="product-prices">
          <!-- Card surcharge container placed FIRST in DOM order -->
          <div class="card-price product-price">
            <span class="price">$ 77,49 (S/ 265,79)</span>
            <span>*Con recargo de 5% adicional por pago con tarjeta de crédito/débito</span>
          </div>
          <!-- Base cash price container placed SECOND in DOM order -->
          <div class="current-price">
            <span class="price product-price">$ 73,80 (S/ 253,13)</span>
            <span>*Sin recargo adicional por pago en Efectivo o Transferencia</span>
          </div>
        </div>
        <div class="product-reference">
          <span class="editable">269645564</span>
        </div>
        <div class="product-availability">
          En stock 4 Artículos
        </div>
      </body>
    </html>
    """
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/ak620.html"

    result = adapter.parse_html(html, url)
    # Base price S/ 253.13 must be selected despite card price being earlier in DOM
    assert result.price == Decimal("253.13")
    assert result.price != Decimal("265.79")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"


def test_computershop_single_element_bundled_text_does_not_mix_prices():
    """Verify that if both cash and card notes are in the same element, card price is stripped."""
    html = """
    <html>
      <body>
        <h1>DeepCool AK620 Digital SE (PN:R-AK620-BKADMN-GJD)</h1>
        <div class="product-prices">
          <div class="current-price">
            $ 73,80 (S/ 253,13) (impuestos inc.) *Sin recargo por pago en Efectivo
            *Con recargo de 5% adicional por pago con tarjeta $ 77,49 (S/ 265,79)
          </div>
        </div>
        <div class="product-reference">
          <span class="editable">269645564</span>
        </div>
        <div class="product-availability">
          En stock 4 Artículos
        </div>
      </body>
    </html>
    """
    adapter = ComputerShopAdapter()
    url = "https://computershopperu.com/producto/ak620.html"

    result = adapter.parse_html(html, url)
    assert result.price == Decimal("253.13")
    assert result.price != Decimal("265.79")
    assert result.currency == "PEN"
    assert result.availability == "in_stock"
