"""Base store adapter interface, domain exceptions and normalized results."""

import re
from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

Availability = Literal["in_stock", "out_of_stock", "unknown"]
PriceCondition = Literal["standard", "cash_or_bank_transfer"]


class ScrapingError(Exception):
    """Base exception for scraping operations."""

    pass


class TransientScrapingError(ScrapingError):
    """Recoverable error (network timeout, rate limit 429, 5xx) that warrants retry."""

    pass


class FatalScrapingError(ScrapingError):
    """Non-recoverable error (HTTP 404, SSRF violation, invalid structure) sent to DLQ."""

    pass


class StoreDisabledError(ScrapingError):
    """Raised when a store is inactive or disabled, to be skipped without DLQ."""

    pass


class StoreBlockedError(ScrapingError):
    """Raised when a store is protected by anti-bot challenges (e.g. Cloudflare HTTP 403).

    Handled cleanly by acknowledging the message with a traceable reason, avoiding
    infinite retries and avoiding DLQ pollution.
    """

    pass


class ScrapedPriceResult(BaseModel):
    """Normalized price observation returned by store adapters."""

    price: Decimal | None = None
    currency: str | None = None
    availability: Availability = "in_stock"
    price_condition: PriceCondition | None = None
    captured_at: datetime
    sku: str | None = None
    mpn: str | None = None
    raw_mpn: str | None = None
    name: str | None = None
    image_url: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def comparison_mpn_key(self) -> str | None:
        """Alphanumeric normalized key for MPN comparison only.

        Never alters or replaces the canonical MPN.
        """
        target = self.raw_mpn or self.mpn
        if not target:
            return None
        return re.sub(r"[^A-Z0-9]", "", target.upper())

    @model_validator(mode="after")
    def validate_price_and_currency(self) -> "ScrapedPriceResult":
        """Validate price consistency according to business rules."""
        if self.price is not None:
            if self.price.is_nan() or self.price.is_infinite():
                raise FatalScrapingError(f"Price must be a finite number: {self.price}")
            if self.price <= 0:
                raise FatalScrapingError(f"Price must be strictly positive: {self.price}")
            if self.price >= Decimal("10000000000"):
                raise FatalScrapingError(f"Price exceeds maximum database range: {self.price}")
            if self.currency not in ("PEN", "USD"):
                raise FatalScrapingError(f"Unsupported or unknown currency: {self.currency}")
        else:
            # If price is None, currency must be None
            self.currency = None
            if self.availability not in ("out_of_stock", "unknown"):
                raise FatalScrapingError(
                    "Products without price must have availability='out_of_stock' or 'unknown'"
                )
        return self


class BaseStoreAdapter(ABC):
    """Interface required for all store scraping adapters."""

    @abstractmethod
    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and normalize product price from a store URL."""
        pass
