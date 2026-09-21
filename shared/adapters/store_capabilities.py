"""Store scraping capabilities and adapter registry metadata shared across services."""

ENABLED_DOMAINS: set[str] = {
    "necs.pe",
    "www.necs.pe",
    "memorykings.pe",
    "www.memorykings.pe",
    "computershopperu.com",
    "www.computershopperu.com",
    "cyccomputer.pe",
    "www.cyccomputer.pe",
}

DISABLED_DOMAINS: set[str] = {
    "sercoplus.com",
    "www.sercoplus.com",
}

OFFLINE_DOMAINS: set[str] = {
    "fake",
}


def normalize_store_domain(domain: str) -> str:
    """Normalize domain string by removing protocol, trailing slashes, and lowercasing."""
    cleaned = domain.strip().lower()
    if cleaned.startswith("https://"):
        cleaned = cleaned[8:]
    elif cleaned.startswith("http://"):
        cleaned = cleaned[7:]
    return cleaned.strip("/")


def is_store_dispatchable(domain: str | None, allow_offline: bool = False) -> tuple[bool, str]:
    """Check whether a store domain has an enabled, active scraping adapter.

    Returns:
        tuple[bool, str]: (is_dispatchable, reason_code)
            reason_code is one of:
            - 'ENABLED': Adapter registered and active.
            - 'NO_DOMAIN': Store has no base_url/domain.
            - 'ADAPTER_DISABLED': Store domain is explicitly disabled/blocked.
            - 'ADAPTER_OFFLINE_ONLY': Store domain is for offline testing only.
            - 'NO_ADAPTER_REGISTERED': No known adapter exists for this domain.
    """
    if not domain:
        return False, "NO_DOMAIN"

    norm = normalize_store_domain(domain)

    if norm in DISABLED_DOMAINS:
        return False, "ADAPTER_DISABLED"

    if norm in OFFLINE_DOMAINS:
        if allow_offline:
            return True, "ENABLED"
        return False, "ADAPTER_OFFLINE_ONLY"

    if norm in ENABLED_DOMAINS:
        return True, "ENABLED"

    return False, "NO_ADAPTER_REGISTERED"
