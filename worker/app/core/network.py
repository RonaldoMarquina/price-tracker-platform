"""Secure HTTP transport layer with SSRF protection, host whitelist, and redirect validation."""

import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

import httpx

from app.adapters.base import FatalScrapingError, StoreBlockedError, TransientScrapingError

logger = logging.getLogger("price-tracker.worker.network")

DEFAULT_SCRAPER_USER_AGENT = (
    "PriceTrackerPlatform/1.0 "
    "(+https://github.com/RonaldoMarquina/price-tracker-platform; academic project)"
)


class SafeHttpClient:
    """HTTP client enforcing HTTPS, domain whitelist, SSRF prevention and validated redirects."""

    def __init__(
        self,
        allowed_hosts: set[str],
        max_redirects: int = 3,
        default_timeout: float = 10.0,
        user_agent: str = DEFAULT_SCRAPER_USER_AGENT,
        dns_resolver: Any = None,
    ) -> None:
        self.allowed_hosts = {h.lower() for h in allowed_hosts}
        self.max_redirects = max_redirects
        self.default_timeout = default_timeout
        self.user_agent = user_agent
        self.dns_resolver = dns_resolver or socket.getaddrinfo

    def validate_url(self, url: str) -> urllib.parse.ParseResult:
        """Validate URL protocol, hostname against allowed aliases, and ensure public IP."""
        parsed = urllib.parse.urlparse(url)

        # 1. Enforce HTTPS only
        if parsed.scheme.lower() != "https":
            raise FatalScrapingError(
                f"Insecure protocol '{parsed.scheme}': only HTTPS URLs are permitted"
            )

        # 2. Enforce allowed hostnames
        hostname = (parsed.hostname or "").lower()
        if not hostname or hostname not in self.allowed_hosts:
            raise FatalScrapingError(
                f"Host '{hostname}' is not in allowed store domains: {sorted(self.allowed_hosts)}"
            )

        # 3. SSRF Protection: Resolve hostname and verify no private/loopback/reserved IPs
        try:
            addr_info = self.dns_resolver(hostname, 443, proto=socket.IPPROTO_TCP)
        except Exception as exc:
            raise FatalScrapingError(f"Failed to resolve hostname '{hostname}': {exc}") from exc

        if not addr_info:
            raise FatalScrapingError(f"DNS resolution returned no addresses for host '{hostname}'")

        for entry in addr_info:
            ip_str = entry[4][0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
            except ValueError as val_err:
                raise FatalScrapingError(f"Invalid resolved IP '{ip_str}': {val_err}") from val_err

            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                raise FatalScrapingError(
                    f"SSRF violation: Host '{hostname}' resolved to prohibited address {ip_str}"
                )

        return parsed

    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        """Execute GET request with redirect validation and status classification."""
        effective_timeout = timeout if timeout is not None else self.default_timeout
        effective_headers = {"User-Agent": self.user_agent}
        if headers:
            effective_headers.update(headers)

        current_url = url
        redirect_count = 0

        with httpx.Client(timeout=effective_timeout, follow_redirects=False) as client:
            while True:
                self.validate_url(current_url)

                try:
                    response = client.get(current_url, headers=effective_headers)
                except httpx.TimeoutException as exc:
                    raise TransientScrapingError(
                        f"Connection timeout requesting {current_url}: {exc}"
                    ) from exc
                except httpx.ConnectError as exc:
                    raise TransientScrapingError(
                        f"Network connection failure requesting {current_url}: {exc}"
                    ) from exc
                except httpx.RequestError as exc:
                    raise TransientScrapingError(
                        f"HTTP request error requesting {current_url}: {exc}"
                    ) from exc

                # Check for HTTP redirect
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise FatalScrapingError(
                            f"HTTP {response.status_code} redirect missing 'Location' header"
                        )

                    next_url = urllib.parse.urljoin(current_url, location)
                    redirect_count += 1
                    if redirect_count > self.max_redirects:
                        raise FatalScrapingError(
                            f"Exceeded max redirects ({self.max_redirects}) for {url}"
                        )

                    logger.debug(
                        "Following validated redirect %d/%d from %s to %s",
                        redirect_count,
                        self.max_redirects,
                        current_url,
                        next_url,
                    )
                    current_url = next_url
                    continue

                # Process final response statuses
                if response.status_code == 404:
                    raise FatalScrapingError(f"Product page not found (HTTP 404): {current_url}")

                if response.status_code == 403:
                    server_header = response.headers.get("server", "").lower()
                    body_snippet = response.text[:2000].lower()
                    has_cf_header = "cf-mitigated" in response.headers
                    is_cloudflare = "cloudflare" in server_header or has_cf_header
                    is_challenge = (
                        "just a moment..." in body_snippet
                        or "challenge-running" in body_snippet
                        or "attention required!" in body_snippet
                        or "cf-browser-verification" in body_snippet
                    )
                    if is_cloudflare or is_challenge:
                        raise StoreBlockedError(
                            f"Store blocked by anti-bot challenge (HTTP 403 Cloudflare): "
                            f"{current_url}"
                        )
                    raise FatalScrapingError(
                        f"Access forbidden (HTTP 403): {current_url}"
                    )

                if response.status_code == 429:
                    raise TransientScrapingError(f"Rate limit exceeded (HTTP 429): {current_url}")

                if 500 <= response.status_code < 600:
                    raise TransientScrapingError(
                        f"Store server error (HTTP {response.status_code}): {current_url}"
                    )

                if response.status_code >= 400:
                    raise FatalScrapingError(
                        f"HTTP client error ({response.status_code}): {current_url}"
                    )

                return response
