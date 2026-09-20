"""Adapter for scraping product prices from Sercoplus (sercoplus.com)."""

import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from bs4 import BeautifulSoup

from app.adapters.base import (
    BaseStoreAdapter,
    FatalScrapingError,
    ScrapedPriceResult,
)
from app.core.network import SafeHttpClient

logger = logging.getLogger("price-tracker.worker.adapters.sercoplus")

ALLOWED_SERCOPLUS_HOSTS = {"sercoplus.com", "www.sercoplus.com"}


class SercoplusAdapter(BaseStoreAdapter):
    """Scraping adapter for Sercoplus Peru e-commerce platform.

    STATUS: Offline-only / Blocked.
    Live scraping from sercoplus.com is currently blocked by Cloudflare anti-bot
    challenges (HTTP 403). In accordance with system design rules, no bypass
    mechanisms (headless browsers, CAPTCHA solvers, residential proxies) are used.
    This adapter is preserved exclusively for offline fixture testing and historical
    validation, and is deactivated by default in the adapter registry.
    """

    is_offline_only: bool = True
    status: str = "blocked"

    def __init__(self, http_client: SafeHttpClient | None = None) -> None:
        self.client = http_client or SafeHttpClient(allowed_hosts=ALLOWED_SERCOPLUS_HOSTS)

    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and extract structured product price data from Sercoplus product URL."""
        response = self.client.get(store_product_url)
        return self.parse_html(response.text, store_product_url)

    def parse_html(self, html_content: str, source_url: str) -> ScrapedPriceResult:
        """Parse Sercoplus HTML extracting strictly the DOM-published PEN price."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Product title
        name_el = (
            soup.select_one("h1.product-detail-name")
            or soup.select_one("h1.h1[itemprop='name']")
            or soup.select_one("h1[itemprop='name']")
            or soup.select_one("h1")
        )
        name = name_el.get_text(strip=True) if name_el else None

        # 2. SKU and MPN
        sku: str | None = None
        mpn: str | None = None
        sku_el = (
            soup.select_one("span[itemprop='sku']")
            or soup.select_one(".product-reference span")
            or soup.select_one(".product-reference")
        )
        if sku_el:
            sku = sku_el.get_text(strip=True).replace("Referencia:", "").strip()

        mpn_el = soup.select_one("span[itemprop='mpn']") or soup.select_one(
            ".product-features .feature-mpn"
        )
        if mpn_el:
            mpn = mpn_el.get_text(strip=True)

        # 3. Image URL
        img_el = (
            soup.select_one("img.js-qv-product-cover")
            or soup.select_one("img[itemprop='image']")
            or soup.select_one("meta[property='og:image']")
        )
        image_url: str | None = None
        if img_el:
            image_url = img_el.get("src") or img_el.get("content")

        # 4. Availability detection
        norm_availability = self._extract_availability(soup)

        # 5. Extract strictly the PEN price from DOM without currency mixing or conversion
        parsed_pen_price = self._extract_pen_price(soup, norm_availability)

        # 6. JSON-LD fallback for metadata (sku/mpn/image) if still missing
        jsonld_data = self._extract_jsonld_product(soup)
        if jsonld_data:
            if not name:
                name = jsonld_data.get("name")
            if not sku and jsonld_data.get("sku"):
                sku = str(jsonld_data["sku"])
            if not mpn and jsonld_data.get("mpn"):
                mpn = str(jsonld_data["mpn"])
            if not image_url and jsonld_data.get("image"):
                img = jsonld_data["image"]
                image_url = (
                    img[0]
                    if isinstance(img, list) and img
                    else (img if isinstance(img, str) else None)
                )

        if not name and parsed_pen_price is None and norm_availability is None:
            raise FatalScrapingError(
                "Sercoplus scraper could not extract product data from HTML: "
                f"structure changed ({source_url})"
            )

        # 7. Apply out_of_stock consistency rule
        effective_avail = norm_availability or "in_stock"
        if effective_avail == "out_of_stock":
            if parsed_pen_price is None:
                final_price = None
                final_currency = None
            else:
                final_price = parsed_pen_price
                final_currency = "PEN"
        else:
            if parsed_pen_price is None:
                raise FatalScrapingError(
                    f"In-stock Sercoplus product missing published PEN price ({source_url})"
                )
            final_price = parsed_pen_price
            final_currency = "PEN"

        return ScrapedPriceResult(
            price=final_price,
            currency=final_currency,
            availability=effective_avail,
            captured_at=datetime.now(timezone.utc),
            sku=sku,
            mpn=mpn,
            name=name,
            image_url=image_url,
        )

    def _extract_pen_price(self, soup: BeautifulSoup, availability: str | None) -> Decimal | None:
        """Extract published PEN price from DOM elements matching S/ pattern."""
        # Find candidate price blocks
        price_containers = soup.select(
            ".current-price, .product-prices, .product-price, span[itemprop='price'], .price"
        )

        for container in price_containers:
            text = container.get_text()
            # Match PEN specific patterns: S/ 390.80 or S/. 862,34 or PEN 390.80
            match = re.search(r"(?:S/\.?|PEN)\s*([\d\.,]+)", text, re.IGNORECASE)
            if match:
                raw_amount = match.group(1)
                try:
                    return self._parse_number(raw_amount)
                except (InvalidOperation, ValueError):
                    continue

        # If no explicit S/ symbol container matched, check itemprop="price" if currency is PEN
        itemprop_el = soup.select_one("span[itemprop='price'], meta[itemprop='price']")
        if itemprop_el:
            curr_el = soup.select_one("meta[itemprop='priceCurrency']")
            if curr_el and curr_el.get("content", "").upper() == "PEN":
                val = itemprop_el.get("content") or itemprop_el.get_text(strip=True)
                match = re.search(r"[\d\.,]+", val)
                if match:
                    try:
                        return self._parse_number(match.group(0))
                    except (InvalidOperation, ValueError):
                        pass

        return None

    def _parse_number(self, raw: str) -> Decimal:
        """Parse number string accounting for thousand and decimal comma/dot formats."""
        cleaned = raw.strip()
        if "." in cleaned and "," in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                # 1.234,56 -> 1234.56
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # 1,234.56 -> 1234.56
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            parts = cleaned.split(",")
            if len(parts[-1]) == 2:
                # 862,34 -> 862.34
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")

        val = Decimal(cleaned)
        if val <= 0:
            raise FatalScrapingError(f"Price must be strictly positive: {val}")
        return val

    def _extract_availability(self, soup: BeautifulSoup) -> str | None:
        """Extract availability status from DOM and JSON-LD."""
        # 1. Check DOM status banner
        avail_el = soup.select_one("#product-availability, .product-availability")
        if avail_el:
            text = avail_el.get_text().lower()
            if (
                "agotado" in text
                or "sin stock" in text
                or "no disponible" in text
                or "fuera de stock" in text
            ):
                return "out_of_stock"
            if "en stock" in text or "disponible" in text:
                return "in_stock"

        # 2. Check Add to Cart button
        cart_btn = soup.select_one("button[data-button-action='add-to-cart'], button.add-to-cart")
        if cart_btn:
            classes = cart_btn.get("class", [])
            if "disabled" in cart_btn.attrs or "disabled" in classes:
                return "out_of_stock"
            return "in_stock"

        # 3. Check JSON-LD offers availability
        jsonld = self._extract_jsonld_product(soup)
        if jsonld and "offers" in jsonld:
            offers = jsonld["offers"]
            offer = (
                offers[0]
                if isinstance(offers, list) and offers
                else (offers if isinstance(offers, dict) else {})
            )
            raw_avail = str(offer.get("availability", "")).lower()
            if "outofstock" in raw_avail or "discontinued" in raw_avail:
                return "out_of_stock"
            if "instock" in raw_avail:
                return "in_stock"

        return None

    def _extract_jsonld_product(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        """Locate schema.org Product JSON-LD block if available."""
        scripts = soup.find_all("script", type="application/ld+json")
        for script in scripts:
            try:
                content = script.string or script.get_text()
                if not content or not content.strip():
                    continue
                data = json.loads(content)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if "@graph" in item and isinstance(item["@graph"], list):
                        for sub in item["@graph"]:
                            if (
                                isinstance(sub, dict)
                                and str(sub.get("@type", "")).lower() == "product"
                            ):
                                return sub
                    if str(item.get("@type", "")).lower() == "product":
                        return item
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return None
