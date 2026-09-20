"""Unit tests for reusable PEN monetary parser."""

import logging
from decimal import Decimal

import pytest

from app.adapters.base import FatalScrapingError
from app.core.price_parser import parse_pen_price


def test_parse_pen_price_standard_dot_decimal():
    """Verify standard format with dot decimal: S/ 253.13."""
    result = parse_pen_price("S/ 253.13")
    assert result == Decimal("253.13")


def test_parse_pen_price_comma_thousands_dot_decimal():
    """Verify format with comma thousands and dot decimal: S/ 1,097.60."""
    result = parse_pen_price("S/ 1,097.60")
    assert result == Decimal("1097.60")


def test_parse_pen_price_standard_comma_decimal():
    """Verify Peruvian format with comma decimal: S/ 253,13."""
    result = parse_pen_price("S/ 253,13")
    assert result == Decimal("253.13")


def test_parse_pen_price_dot_thousands_comma_decimal():
    """Verify format with dot thousands and comma decimal: S/ 1.097,60."""
    result = parse_pen_price("S/ 1.097,60")
    assert result == Decimal("1097.60")


def test_parse_pen_price_with_parentheses_and_prefixes():
    """Verify format in Prestashop style: $ 223,00 (S/ 764,89)."""
    result = parse_pen_price("$ 223,00 (S/ 764,89) (impuestos inc.)")
    assert result == Decimal("764.89")


def test_parse_pen_price_repeated_identical_amounts():
    """Verify that repeated identical PEN amounts do not cause ambiguity."""
    result = parse_pen_price("Oferta: S/ 450.00 - Precio final S/ 450.00")
    assert result == Decimal("450.00")


def test_parse_pen_price_atypical_high_value_logs_warning(caplog):
    """Verify atypical value S/ 1.711,57 is preserved and logs audit warning."""
    with caplog.at_level(logging.WARNING):
        result = parse_pen_price("S/ 1.711,57")
        assert result == Decimal("1711.57")
        assert not caplog.records  # Under 10,000 threshold

    with caplog.at_level(logging.WARNING):
        result_high = parse_pen_price("S/ 15,499.90")
        assert result_high == Decimal("15499.90")
        assert any("Atypical high price observed" in r.message for r in caplog.records)


def test_parse_pen_price_rejects_empty_or_none():
    """Verify empty or None inputs raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="cannot be None"):
        parse_pen_price(None)

    with pytest.raises(FatalScrapingError, match="Price text is empty"):
        parse_pen_price("   ")


def test_parse_pen_price_rejects_zero_or_negative():
    """Verify zero or negative values raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="strictly positive"):
        parse_pen_price("S/ 0.00")

    with pytest.raises(FatalScrapingError, match="strictly positive"):
        parse_pen_price("S/ -15.50")


def test_parse_pen_price_rejects_missing_pen_currency():
    """Verify prices without PEN indicator raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="No PEN price indicator found"):
        parse_pen_price("$ 250.00 (USD)")


def test_parse_pen_price_rejects_ambiguous_multiple_amounts():
    """Verify differing PEN amounts raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="Multiple ambiguous PEN amounts"):
        parse_pen_price("Antes: S/ 350.00 - Ahora: S/ 299.00")


def test_parse_pen_price_rejects_exceeding_max_limit():
    """Verify prices exceeding Numeric(12, 2) capacity raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="exceeds maximum database limit"):
        parse_pen_price("S/ 99,999,999,999.00")


def test_parse_pen_price_rejects_malformed_separators():
    """Verify malformed consecutive separators raise FatalScrapingError."""
    with pytest.raises(FatalScrapingError, match="Malformed numeric format"):
        parse_pen_price("S/ 250..00")
