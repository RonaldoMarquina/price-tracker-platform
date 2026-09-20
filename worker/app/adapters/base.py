"""Base store adapter interface and domain exceptions."""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ScrapedPriceResult(BaseModel):
    """Normalized price observation returned by store adapters."""

    price: Decimal
    currency: str = "PEN"
    availability: str = "in_stock"
    captured_at: datetime

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ScrapingError(Exception):
    """Base exception for scraping operations."""

    pass


class TransientScrapingError(ScrapingError):
    """Recoverable error (network timeout, rate limit) that warrants retry."""

    pass


class FatalScrapingError(ScrapingError):
    """Non-recoverable error (page removed, blocked) that should go to DLQ."""

    pass


class BaseStoreAdapter(ABC):
    """Interface required for all store scraping adapters."""

    @abstractmethod
    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and normalize product price from a store URL."""
        pass
