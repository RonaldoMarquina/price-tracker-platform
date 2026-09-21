"""Registry mapping store domains to specific scraping adapter instances."""

import logging

from shared.adapters.store_capabilities import (
    DISABLED_DOMAINS as DEFAULT_DISABLED_DOMAINS,
)
from shared.adapters.store_capabilities import (
    normalize_store_domain,
)

from app.adapters.base import (
    BaseStoreAdapter,
    FatalScrapingError,
    StoreDisabledError,
)
from app.adapters.computershop_adapter import ComputerShopAdapter
from app.adapters.cyc_adapter import CycComputerAdapter
from app.adapters.fake_store_adapter import FakeStoreAdapter
from app.adapters.memorykings_adapter import MemoryKingsAdapter
from app.adapters.necs_adapter import NecsAdapter
from app.adapters.sercoplus_adapter import SercoplusAdapter

logger = logging.getLogger("price-tracker.worker.adapters.registry")


class AdapterRegistry:
    """Registry maintaining active and disabled store adapters keyed by domain."""

    def __init__(
        self,
        adapters: dict[str, BaseStoreAdapter] | None = None,
        disabled_domains: set[str] | None = None,
    ) -> None:
        initial_disabled = (
            DEFAULT_DISABLED_DOMAINS if disabled_domains is None else disabled_domains
        )
        self.disabled_domains = {d.lower() for d in initial_disabled}
        self._adapters: dict[str, BaseStoreAdapter] = {}

        if adapters is not None:
            for domain, adapter in adapters.items():
                self.register(domain, adapter)
        else:
            # Default initialization with real adapters
            necs = NecsAdapter()
            memorykings = MemoryKingsAdapter()
            computershop = ComputerShopAdapter()
            cyc = CycComputerAdapter()
            sercoplus = SercoplusAdapter()
            fake = FakeStoreAdapter()

            self.register("necs.pe", necs)
            self.register("www.necs.pe", necs)
            self.register("memorykings.pe", memorykings)
            self.register("www.memorykings.pe", memorykings)
            self.register("computershopperu.com", computershop)
            self.register("www.computershopperu.com", computershop)
            self.register("cyccomputer.pe", cyc)
            self.register("www.cyccomputer.pe", cyc)
            self.register("sercoplus.com", sercoplus)
            self.register("www.sercoplus.com", sercoplus)
            self.register("fake", fake)

    def register(self, domain: str, adapter: BaseStoreAdapter) -> None:
        """Register a store adapter for a domain."""
        norm_domain = self._normalize_domain(domain)
        self._adapters[norm_domain] = adapter

    def disable_domain(self, domain: str) -> None:
        """Disable a domain in the registry (circuit breaker / operator block)."""
        norm = self._normalize_domain(domain)
        self.disabled_domains.add(norm)
        logger.warning("Domain '%s' disabled in adapter registry", norm)

    def enable_domain(self, domain: str) -> None:
        """Enable a previously disabled domain in the registry."""
        norm = self._normalize_domain(domain)
        self.disabled_domains.discard(norm)
        logger.info("Domain '%s' enabled in adapter registry", norm)

    def get_adapter(self, domain: str) -> BaseStoreAdapter:
        """Resolve adapter for a store domain, checking if disabled."""
        norm_domain = self._normalize_domain(domain)

        # Check if store domain is disabled
        if norm_domain in self.disabled_domains:
            raise StoreDisabledError(
                f"Scraping adapter for domain '{norm_domain}' is currently disabled"
            )

        adapter = self._adapters.get(norm_domain)
        if not adapter:
            raise FatalScrapingError(
                f"No scraping adapter registered for store domain '{domain}' "
                f"(normalized: '{norm_domain}')"
            )

        return adapter

    def _normalize_domain(self, domain: str) -> str:
        """Normalize domain string by stripping protocols, slashes, and whitespace."""
        return normalize_store_domain(domain)

    def is_domain_dispatchable(self, domain: str, allow_offline: bool = False) -> tuple[bool, str]:
        """Check if a domain is registered and active for dispatching."""
        norm = self._normalize_domain(domain)
        if norm in self.disabled_domains:
            return False, "ADAPTER_DISABLED"
        if norm == "fake" and not allow_offline:
            return False, "ADAPTER_OFFLINE_ONLY"
        if norm not in self._adapters:
            return False, "NO_ADAPTER_REGISTERED"
        return True, "ENABLED"


# Default global registry instance
default_registry = AdapterRegistry()
