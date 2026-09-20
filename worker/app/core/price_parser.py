"""Reusable and robust monetary parser for Peruvian currency (PEN)."""

import logging
import re
from decimal import Decimal, InvalidOperation

from app.adapters.base import FatalScrapingError

logger = logging.getLogger(__name__)

MAX_PRICE_ALLOWED = Decimal("10000000000")  # Corresponds to Numeric(12, 2) max
ATYPICAL_PRICE_THRESHOLD = Decimal("10000")  # Threshold to log warning for audit


def parse_pen_price(raw_text: str | None) -> Decimal:
    """Parse and normalize a PEN monetary amount from raw store text.

    Supported formats:
        - S/ 253.13
        - S/ 1,097.60
        - S/ 253,13
        - S/ 1.097,60

    Rejects:
        - Empty or whitespace strings
        - Zero or negative amounts
        - Multiple ambiguous PEN amounts
        - Formats that cannot be interpreted with certainty
        - NaN, Infinite, or amounts exceeding database capacity (Numeric(12, 2))
    """
    if raw_text is None:
        raise FatalScrapingError("Price text cannot be None")

    text = raw_text.strip()
    if not text:
        raise FatalScrapingError("Price text is empty")

    # Match PEN patterns: "S/ 1,097.60", "S/. 253,13", "PEN 253.13", "(S/ 764,89)", "S/ -15.50"
    # We look for explicit PEN / S/ indicators
    pen_pattern = re.compile(r"(?:S\/?\.?|PEN)\s*([-\d\.,]+)", re.IGNORECASE)
    matches = pen_pattern.findall(text)

    if not matches:
        raise FatalScrapingError(f"No PEN price indicator found in text: '{text}'")

    # Clean candidate numeric strings
    candidates = []
    for m in matches:
        cleaned_str = m.strip()
        # Ensure it has digits
        if re.search(r"\d", cleaned_str):
            candidates.append(cleaned_str)

    if not candidates:
        raise FatalScrapingError(f"No valid numeric price found in PEN match: '{text}'")

    # If multiple candidates found, parse them all and check if they are unambiguous
    parsed_values = set()
    for candidate in candidates:
        parsed_val = _parse_numeric_amount(candidate)
        parsed_values.add(parsed_val)

    if len(parsed_values) > 1:
        # If there are multiple differing PEN values, it's ambiguous
        raise FatalScrapingError(
            f"Multiple ambiguous PEN amounts found in text: '{text}' -> {parsed_values}"
        )

    final_price = parsed_values.pop()

    # Range and sanity validations
    if final_price <= 0:
        raise FatalScrapingError(f"Price must be strictly positive: {final_price}")

    if final_price >= MAX_PRICE_ALLOWED:
        raise FatalScrapingError(
            f"Price exceeds maximum database limit of {MAX_PRICE_ALLOWED}: {final_price}"
        )

    if final_price >= ATYPICAL_PRICE_THRESHOLD:
        logger.warning(
            "Atypical high price observed (%s PEN). Preserving faithful published value.",
            final_price,
        )

    return final_price


def _parse_numeric_amount(candidate: str) -> Decimal:
    """Parse numeric string with comma/dot decimal or thousands separators."""
    # Strip non-numeric and non-separator chars except minus
    clean = re.sub(r"[^\d,\.\-]", "", candidate).strip()
    if not clean:
        raise FatalScrapingError("Empty numeric string after cleaning")

    # If minus appears not at the beginning or multiple times, reject
    if clean.count("-") > 1 or ("-" in clean and not clean.startswith("-")):
        raise FatalScrapingError(f"Malformed negative price format: '{clean}'")

    # Validate that it cannot end or start with multiple consecutive separators
    if re.search(r"[\.,]{2,}", clean):
        raise FatalScrapingError(f"Malformed numeric format with multiple separators: '{clean}'")

    try:
        if "." in clean and "," in clean:
            # Check which separator comes last
            if clean.rfind(",") > clean.rfind("."):
                # 1.097,60 -> dot is thousands, comma is decimal
                clean = clean.replace(".", "").replace(",", ".")
            else:
                # 1,097.60 -> comma is thousands, dot is decimal
                clean = clean.replace(",", "")
        elif "," in clean:
            # Only comma exists: e.g. 253,13
            clean = clean.replace(",", ".")
        # else: only dot exists (253.13) or integer (250)

        value = Decimal(clean)
    except (InvalidOperation, ValueError) as err:
        raise FatalScrapingError(
            f"Unable to parse decimal price from '{candidate}': {err}"
        ) from err

    if value.is_nan() or value.is_infinite():
        raise FatalScrapingError(f"Invalid non-finite decimal value: {value}")

    return value
