"""Adapter for scraping product prices from NECS Ayacucho (necs.pe)."""

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
    validate_store_image_url,
)
from app.core.network import SafeHttpClient

logger = logging.getLogger("price-tracker.worker.adapters.necs")

ALLOWED_NECS_HOSTS = {"necs.pe", "www.necs.pe"}


class NecsAdapter(BaseStoreAdapter):
    """Scraping adapter for NECS Ayacucho e-commerce platform."""

    def __init__(self, http_client: SafeHttpClient | None = None) -> None:
        self.client = http_client or SafeHttpClient(allowed_hosts=ALLOWED_NECS_HOSTS)

    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and extract structured product price data from NECS product URL."""
        response = self.client.get(store_product_url)
        return self.parse_html(response.text, store_product_url)

    def parse_html(self, html_content: str, source_url: str) -> ScrapedPriceResult:
        """Parse raw HTML content into normalized ScrapedPriceResult."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Try structured data: JSON-LD
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
            sku = str(jsonld_data["sku"]) if jsonld_data.get("sku") else None
            mpn = str(jsonld_data["mpn"]) if jsonld_data.get("mpn") else None
            image = jsonld_data.get("image")
            if isinstance(image, list) and image:
                image_url = image[0]
            elif isinstance(image, str):
                image_url = image

            offers = jsonld_data.get("offers")
            if isinstance(offers, list) and offers:
                offer = offers[0]
            elif isinstance(offers, dict):
                offer = offers
            else:
                offer = {}

            if offer:
                raw_price = str(offer.get("price")) if offer.get("price") is not None else None
                raw_currency = offer.get("priceCurrency")
                raw_availability = offer.get("availability")

        # 2. Fallbacks for missing fields from DOM
        if not name:
            name_el = (
                soup.select_one("h1.product-detail-name")
                or soup.select_one("h1.product-title")
                or soup.select_one("h1[itemprop='name']")
                or soup.select_one("h1")
            )
            if name_el:
                name = name_el.get_text(strip=True)

        if not sku:
            sku_el = soup.select_one("span[itemprop='sku']") or soup.select_one(
                ".product-reference span"
            )
            if sku_el:
                sku = sku_el.get_text(strip=True)

        if not image_url:
            img_el = (
                soup.select_one("img.js-qv-product-cover")
                or soup.select_one("img[itemprop='image']")
                or soup.select_one("meta[property='og:image']")
            )
            if img_el:
                image_url = img_el.get("src") or img_el.get("content")

        if not raw_price:
            price_el = (
                soup.select_one(".product-prices .current-price")
                or soup.select_one("span[itemprop='price']")
                or soup.select_one(".product-price")
            )
            if price_el:
                content_val = price_el.get("content")
                if content_val:
                    raw_price = content_val
                else:
                    text_val = price_el.get_text(strip=True)
                    match = re.search(r"[\d\.,]+", text_val)
                    if match:
                        raw_price = match.group(0)

        if not raw_availability:
            avail_el = soup.select_one("#product-availability") or soup.select_one(
                ".product-availability"
            )
            if avail_el:
                raw_availability = avail_el.get_text(strip=True)
            else:
                cart_btn = soup.select_one("button.add-to-cart")
                if cart_btn and (
                    "disabled" in cart_btn.attrs or "disabled" in cart_btn.get("class", [])
                ):
                    raw_availability = "out_of_stock"

        # Validate minimum presence of page structure
        if not name and not raw_price and not raw_availability:
            raise FatalScrapingError(
                "NECS scraper could not extract product data from HTML: "
                f"structure changed ({source_url})"
            )

        # 3. Determine availability
        norm_availability = self._normalize_availability(raw_availability)

        # 4. Determine currency
        currency = raw_currency.strip().upper() if raw_currency else "PEN"
        if currency not in ("PEN", "USD"):
            raise FatalScrapingError(
                f"Unsupported or unknown currency '{currency}' in {source_url}"
            )

        # 5. Parse price decimal
        parsed_price: Decimal | None = None
        if raw_price:
            cleaned_price = (
                raw_price.strip()
                .replace("S/.", "")
                .replace("S/", "")
                .replace("PEN", "")
                .replace("$", "")
                .strip()
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
                    # Non-positive price
                    if norm_availability == "in_stock":
                        raise FatalScrapingError(
                            f"Price must be strictly positive for in_stock product: {val}"
                        )
                    parsed_price = None
            except InvalidOperation as exc:
                if norm_availability == "in_stock":
                    raise FatalScrapingError(f"Invalid price value '{raw_price}': {exc}") from exc
                parsed_price = None

        # 6. Apply out_of_stock rule
        if norm_availability == "out_of_stock":
            if parsed_price is None:
                final_price = None
                final_currency = None
            else:
                final_price = parsed_price
                final_currency = currency
        else:
            if parsed_price is None:
                raise FatalScrapingError(f"In-stock product missing valid price: {source_url}")
            final_price = parsed_price
            final_currency = currency

        validated_image_url = validate_store_image_url(image_url, ALLOWED_NECS_HOSTS)

        return ScrapedPriceResult(
            price=final_price,
            currency=final_currency,
            availability=norm_availability,
            price_condition="standard",
            captured_at=datetime.now(timezone.utc),
            sku=sku,
            mpn=mpn,
            name=name,
            image_url=validated_image_url,
        )

    def _extract_jsonld_product(self, soup: BeautifulSoup) -> dict[str, Any] | None:
        """Locate and parse schema.org Product JSON-LD block."""
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
                        for sub_item in item["@graph"]:
                            if isinstance(sub_item, dict) and self._is_product_type(
                                sub_item.get("@type")
                            ):
                                return sub_item
                    if self._is_product_type(item.get("@type")):
                        return item
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
        return None

    def _is_product_type(self, type_val: Any) -> bool:
        if isinstance(type_val, str) and type_val.lower() == "product":
            return True
        if isinstance(type_val, list) and any(str(t).lower() == "product" for t in type_val):
            return True
        return False

    def _normalize_availability(self, raw: str | None) -> str:
        if not raw:
            return "in_stock"
        lower = raw.lower()
        if (
            "outofstock" in lower
            or "out of stock" in lower
            or "agotado" in lower
            or "sin stock" in lower
            or "no disponible" in lower
        ):
            return "out_of_stock"
        return "in_stock"
