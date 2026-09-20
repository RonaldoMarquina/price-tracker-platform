"""Base store adapter interface, domain exceptions and normalized results."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


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
    availability: str = "in_stock"
    captured_at: datetime
    sku: str | None = None
    mpn: str | None = None
    name: str | None = None
    image_url: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def validate_price_and_currency(self) -> "ScrapedPriceResult":
        """Validate price consistency according to business rules."""
        if self.price is not None:
            if self.price <= 0:
                raise FatalScrapingError(f"Price must be strictly positive: {self.price}")
            if self.currency not in ("PEN", "USD"):
                raise FatalScrapingError(f"Unsupported or unknown currency: {self.currency}")
        else:
            # If price is None, currency must be None
            self.currency = None
            if self.availability != "out_of_stock":
                raise FatalScrapingError(
                    "Products without published price must have availability='out_of_stock'"
                )
        return self


class BaseStoreAdapter(ABC):
    """Interface required for all store scraping adapters."""

    @abstractmethod
    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and normalize product price from a store URL."""
        pass
