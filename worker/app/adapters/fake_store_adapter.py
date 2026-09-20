"""Deterministic fake store adapter for offline testing."""

import hashlib
from datetime import datetime, timezone
from decimal import Decimal

from app.adapters.base import (
    BaseStoreAdapter,
    FatalScrapingError,
    ScrapedPriceResult,
    TransientScrapingError,
)


class FakeStoreAdapter(BaseStoreAdapter):
    """Fake store adapter that generates deterministic price data without internet access."""

    def __init__(self, default_price: Decimal = Decimal("499.90")) -> None:
        self.default_price = default_price

    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Return controlled pricing based on input URL or trigger simulated failures."""
        if "simulate-transient-error" in store_product_url:
            raise TransientScrapingError(
                "Simulated transient connection timeout in fake store adapter."
            )

        if "simulate-fatal-error" in store_product_url:
            raise FatalScrapingError("Simulated permanent HTTP 404 product deleted.")

        # Deterministic variation based on URL hash for variety in tests
        url_hash = int(hashlib.md5(store_product_url.encode()).hexdigest(), 16)
        variation = Decimal(url_hash % 100) / Decimal("10")
        calculated_price = (self.default_price + variation).quantize(Decimal("0.01"))

        return ScrapedPriceResult(
            price=calculated_price,
            currency="PEN",
            availability="in_stock",
            price_condition="standard",
            captured_at=datetime.now(timezone.utc),
        )
