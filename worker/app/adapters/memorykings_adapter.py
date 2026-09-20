"""Adapter for scraping product prices from Memory Kings (memorykings.pe)."""

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

logger = logging.getLogger("price-tracker.worker.adapters.memorykings")

ALLOWED_MEMORYKINGS_HOSTS = {"memorykings.pe", "www.memorykings.pe"}


class MemoryKingsAdapter(BaseStoreAdapter):
    """Scraping adapter for Memory Kings Peru e-commerce platform.

    Uses Schema.org JSON-LD as primary data source, with HTML/DOM as fallback.
    Extracts strictly the official PEN price (ignoring reference USD prices).
    Only validates image URLs without downloading media from the CDN.
    """

    def __init__(self, http_client: SafeHttpClient | None = None) -> None:
        self.client = http_client or SafeHttpClient(allowed_hosts=ALLOWED_MEMORYKINGS_HOSTS)

    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and extract structured product price data from Memory Kings product URL."""
        response = self.client.get(store_product_url)
        return self.parse_html(response.text, store_product_url)

    def parse_html(self, html_content: str, source_url: str) -> ScrapedPriceResult:
        """Parse raw HTML content into normalized ScrapedPriceResult."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Primary data source: Schema.org JSON-LD
        jsonld_data = self._extract_jsonld_product(soup)

        name: str | None = None
        sku: str | None = None
        mpn: str | None = None
        image_url: str | None = None
        raw_price: str | None = None
        raw_currency: str | None = None
        raw_availability: str | None = None

        if jsonld_data:
            name = jsonld_data.get("name")
            if jsonld_data.get("sku"):
                sku = str(jsonld_data["sku"]).strip()
            if jsonld_data.get("mpn"):
                mpn = str(jsonld_data["mpn"]).strip()

            image = jsonld_data.get("image")
            if isinstance(image, list) and image:
                image_url = self._validate_image_url(image[0])
            elif isinstance(image, str):
                image_url = self._validate_image_url(image)

            offers = jsonld_data.get("offers")
            if isinstance(offers, list) and offers:
                offer = offers[0]
            elif isinstance(offers, dict):
                offer = offers
            else:
                offer = {}

            if offer:
                if offer.get("price") is not None:
                    raw_price = str(offer.get("price"))
                raw_currency = offer.get("priceCurrency")
                raw_availability = offer.get("availability")

        # 2. Secondary fallback: HTML/CSS selectors
        if not name:
            h1_el = soup.find("h1")
            if h1_el:
                name = h1_el.get_text(strip=True)

        if not sku:
            # Memory Kings embeds product ID in URL: /producto/{id}/{slug}
            match = re.search(r"/producto/(\d+)", source_url)
            if match:
                sku = match.group(1)
            else:
                sku_el = soup.select_one("span[itemprop='sku']") or soup.select_one(".product-sku")
                if sku_el:
                    sku = sku_el.get_text(strip=True)

        if not mpn:
            mpn_el = soup.select_one("span[itemprop='mpn']") or soup.select_one(".product-mpn")
            if mpn_el:
                mpn = mpn_el.get_text(strip=True)

        if not image_url:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                image_url = self._validate_image_url(og_img.get("content"))

        if not raw_price:
            # Look for PEN price in DOM (ignoring USD portion)
            # e.g.: <div class="price pt-1">$ 115.00 ó S/ 392.00</div>
            price_containers = soup.find_all(class_=lambda c: c and "price" in c.lower())
            for container in price_containers:
                container_text = container.get_text(strip=True)
                pen_match = re.search(r"S/\s*([\d,.]+)", container_text)
                if pen_match:
                    raw_price = pen_match.group(1)
                    raw_currency = "PEN"
                    break

        if not raw_availability:
            # Check stock indicators in DOM
            stock_el = soup.find(class_=lambda c: c and "stock" in c.lower())
            if stock_el:
                raw_availability = stock_el.get_text(strip=True)

        # Validate minimum presence of page structure
        if not name and not raw_price and not raw_availability:
            raise FatalScrapingError(
                "Memory Kings scraper could not extract product data from HTML: "
                f"structure changed ({source_url})"
            )

        # 3. Determine availability
        norm_availability = self._normalize_availability(raw_availability)

        # 4. Determine and validate currency (must be PEN)
        currency = raw_currency.strip().upper() if raw_currency else "PEN"
        if currency != "PEN":
            raise FatalScrapingError(
                f"Unsupported currency '{currency}' for Memory Kings (expected PEN) in {source_url}"
            )

        # 5. Parse price decimal
        parsed_price: Decimal | None = None
        if raw_price:
            cleaned_price = (
                raw_price.strip().replace("S/.", "").replace("S/", "").replace("PEN", "").strip()
            )
            try:
                # Handle comma decimal vs dot decimal
                if "." in cleaned_price and "," in cleaned_price:
                    if cleaned_price.rfind(",") > cleaned_price.rfind("."):
                        cleaned_price = cleaned_price.replace(".", "").replace(",", ".")
                    else:
                        cleaned_price = cleaned_price.replace(",", "")
                elif "," in cleaned_price:
                    parts = cleaned_price.split(",")
                    if len(parts[-1]) == 2:
                        cleaned_price = cleaned_price.replace(",", ".")
                    else:
                        cleaned_price = cleaned_price.replace(",", "")

                val = Decimal(cleaned_price)
                if val > 0:
                    parsed_price = val
                else:
                    if norm_availability == "in_stock":
                        raise FatalScrapingError(
                            f"Price must be strictly positive for in_stock product: {val}"
                        )
                    parsed_price = None
            except InvalidOperation as exc:
                raise FatalScrapingError(
                    f"Invalid price format '{raw_price}' in {source_url}: {exc}"
                ) from exc
        else:
            if norm_availability == "in_stock":
                raise FatalScrapingError(
                    f"Product marked in_stock but missing price in {source_url}"
                )
            parsed_price = None

        final_currency = "PEN" if parsed_price is not None else None

        return ScrapedPriceResult(
            price=parsed_price,
            currency=final_currency,
            availability=norm_availability,
            price_condition="standard",
            captured_at=datetime.now(timezone.utc),
            sku=sku,
            mpn=mpn,
            name=name.strip() if name else None,
            image_url=image_url,
        )

    def _extract_jsonld_product(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        """Extract and parse Schema.org Product item from JSON-LD script tags."""
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string)
            except Exception:
                continue

            if isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                # Handle nested @graph
                graph = data.get("@graph")
                if isinstance(graph, list):
                    for item in graph:
                        if isinstance(item, dict) and item.get("@type") == "Product":
                            return item
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("@type") == "Product":
                        return item
        return None

    def _normalize_availability(self, raw_availability: str | None) -> str:
        """Normalize raw availability into standard 'in_stock' or 'out_of_stock'."""
        if not raw_availability:
            return "in_stock"

        norm = raw_availability.lower().strip()
        if "instock" in norm or "in stock" in norm or "disponible" in norm:
            return "in_stock"
        if (
            "outofstock" in norm
            or "out of stock" in norm
            or "agotado" in norm
            or "sin stock" in norm
            or "no disponible" in norm
        ):
            return "out_of_stock"

        return "in_stock"

    def _validate_image_url(self, url: Any) -> str | None:
        """Validate that image URL is well-formed HTTPS string without downloading."""
        if not isinstance(url, str):
            return None
        cleaned = url.strip()
        if cleaned.startswith("https://") or cleaned.startswith("http://"):
            return cleaned
        return None
