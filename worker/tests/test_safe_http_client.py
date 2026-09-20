"""Unit tests for SafeHttpClient security, anti-SSRF, and redirect policies."""

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.adapters.base import FatalScrapingError, StoreBlockedError, TransientScrapingError
from app.core.network import SafeHttpClient


def mock_public_dns(hostname: str, port: int, **kwargs):
    """Simulate DNS resolving to a public IPv4 address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]


def mock_private_dns(hostname: str, port: int, **kwargs):
    """Simulate DNS resolving to a private RFC 1918 address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.50", port))]


def mock_loopback_dns(hostname: str, port: int, **kwargs):
    """Simulate DNS resolving to loopback."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]


def mock_metadata_dns(hostname: str, port: int, **kwargs):
    """Simulate DNS resolving to cloud link-local metadata address."""
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]


def test_safe_http_client_rejects_insecure_scheme():
    """Client must reject non-HTTPS URLs."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"})
    with pytest.raises(FatalScrapingError, match="only HTTPS URLs are permitted"):
        client.get("http://necs.pe/products/10744")


def test_safe_http_client_rejects_unauthorized_domain():
    """Client must reject domains not in whitelist."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"})
    with pytest.raises(FatalScrapingError, match="not in allowed store domains"):
        client.get("https://malicious-site.com/exploit")


def test_safe_http_client_blocks_loopback_ssrf():
    """Client must block host resolving to 127.0.0.1."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"}, dns_resolver=mock_loopback_dns)
    with pytest.raises(FatalScrapingError, match="SSRF violation"):
        client.get("https://necs.pe/products/1")


def test_safe_http_client_blocks_private_network_ssrf():
    """Client must block host resolving to private IP 192.168.x.x."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"}, dns_resolver=mock_private_dns)
    with pytest.raises(FatalScrapingError, match="SSRF violation"):
        client.get("https://necs.pe/products/1")


def test_safe_http_client_blocks_metadata_endpoint_ssrf():
    """Client must block host resolving to AWS/Cloud link-local 169.254.x.x."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"}, dns_resolver=mock_metadata_dns)
    with pytest.raises(FatalScrapingError, match="SSRF violation"):
        client.get("https://necs.pe/products/1")


def test_safe_http_client_blocks_cross_domain_redirect():
    """Client must abort and raise FatalScrapingError if redirect points outside whitelist."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"}, dns_resolver=mock_public_dns)

    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 302
    mock_resp.headers = {"Location": "https://attacker.com/steal-data"}

    with patch.object(httpx.Client, "get", return_value=mock_resp):
        with pytest.raises(FatalScrapingError, match="not in allowed store domains"):
            client.get("https://necs.pe/products/1")


def test_safe_http_client_allows_authorized_alias_redirect():
    """Client must follow valid redirects between whitelisted aliases."""
    client = SafeHttpClient(
        allowed_hosts={"necs.pe", "www.necs.pe"},
        dns_resolver=mock_public_dns,
    )

    redirect_resp = MagicMock(spec=httpx.Response)
    redirect_resp.status_code = 301
    redirect_resp.headers = {"Location": "https://www.necs.pe/products/1"}

    final_resp = MagicMock(spec=httpx.Response)
    final_resp.status_code = 200
    final_resp.text = "<html>OK</html>"

    with patch.object(httpx.Client, "get", side_effect=[redirect_resp, final_resp]):
        resp = client.get("https://necs.pe/products/1")
        assert resp.status_code == 200
        assert resp.text == "<html>OK</html>"


def test_safe_http_client_allows_computershop_domain_and_redirect():
    """Client permits computershopperu.com and follows redirect to www alias."""
    client = SafeHttpClient(
        allowed_hosts={"computershopperu.com", "www.computershopperu.com"},
        dns_resolver=mock_public_dns,
    )

    redirect_resp = MagicMock(spec=httpx.Response)
    redirect_resp.status_code = 301
    redirect_resp.headers = {"Location": "https://www.computershopperu.com/producto/123.html"}

    final_resp = MagicMock(spec=httpx.Response)
    final_resp.status_code = 200
    final_resp.text = "<html>Computer Shop</html>"

    with patch.object(httpx.Client, "get", side_effect=[redirect_resp, final_resp]):
        resp = client.get("https://computershopperu.com/producto/123.html")
        assert resp.status_code == 200
        assert resp.text == "<html>Computer Shop</html>"


def test_safe_http_client_allows_cyc_domain_and_redirect():
    """Client permits cyccomputer.pe and follows redirect to www alias."""
    client = SafeHttpClient(
        allowed_hosts={"cyccomputer.pe", "www.cyccomputer.pe"},
        dns_resolver=mock_public_dns,
    )

    redirect_resp = MagicMock(spec=httpx.Response)
    redirect_resp.status_code = 301
    redirect_resp.headers = {"Location": "https://www.cyccomputer.pe/producto/123.html"}

    final_resp = MagicMock(spec=httpx.Response)
    final_resp.status_code = 200
    final_resp.text = "<html>CyC Computer</html>"

    with patch.object(httpx.Client, "get", side_effect=[redirect_resp, final_resp]):
        resp = client.get("https://cyccomputer.pe/producto/123.html")
        assert resp.status_code == 200
        assert resp.text == "<html>CyC Computer</html>"


def test_safe_http_client_exceeds_max_redirects():
    """Client must abort when redirects exceed limit."""
    client = SafeHttpClient(
        allowed_hosts={"necs.pe"},
        max_redirects=2,
        dns_resolver=mock_public_dns,
    )

    redirect_resp = MagicMock(spec=httpx.Response)
    redirect_resp.status_code = 302
    redirect_resp.headers = {"Location": "https://necs.pe/products/loop"}

    with patch.object(httpx.Client, "get", return_value=redirect_resp):
        with pytest.raises(FatalScrapingError, match="Exceeded max redirects"):
            client.get("https://necs.pe/products/start")


def test_safe_http_client_maps_statuses_correctly():
    """Check 404, 429, 500 mapping."""
    client = SafeHttpClient(allowed_hosts={"necs.pe"}, dns_resolver=mock_public_dns)

    resp_404 = MagicMock(spec=httpx.Response, status_code=404)
    with patch.object(httpx.Client, "get", return_value=resp_404):
        with pytest.raises(FatalScrapingError, match="HTTP 404"):
            client.get("https://necs.pe/products/404")

    resp_429 = MagicMock(spec=httpx.Response, status_code=429)
    with patch.object(httpx.Client, "get", return_value=resp_429):
        with pytest.raises(TransientScrapingError, match="HTTP 429"):
            client.get("https://necs.pe/products/rate-limit")

    resp_503 = MagicMock(spec=httpx.Response, status_code=503)
    with patch.object(httpx.Client, "get", return_value=resp_503):
        with pytest.raises(TransientScrapingError, match="HTTP 503"):
            client.get("https://necs.pe/products/maintenance")


def test_safe_http_client_detects_cloudflare_challenge_raises_store_blocked():
    """HTTP 403 with Cloudflare challenge headers or body raises StoreBlockedError."""
    client = SafeHttpClient(allowed_hosts={"sercoplus.com"}, dns_resolver=mock_public_dns)

    resp_cf = MagicMock(spec=httpx.Response, status_code=403)
    resp_cf.headers = {"server": "cloudflare"}
    resp_cf.text = (
        "<!DOCTYPE html><html><title>Just a moment...</title>"
        "<body>Checking your browser before accessing sercoplus.com</body></html>"
    )

    with patch.object(httpx.Client, "get", return_value=resp_cf):
        with pytest.raises(StoreBlockedError, match="anti-bot challenge"):
            client.get("https://sercoplus.com/producto/123")
