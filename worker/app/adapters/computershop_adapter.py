"""Scraping adapter for Computer Shop Perú (computershopperu.com)."""

import logging
import re
from datetime import datetime, timezone
from decimal import Decimal

from bs4 import BeautifulSoup

from app.adapters.base import (
    Availability,
    BaseStoreAdapter,
    FatalScrapingError,
    ScrapedPriceResult,
)
from app.core.network import SafeHttpClient
from app.core.price_parser import parse_pen_price

logger = logging.getLogger(__name__)

ALLOWED_COMPUTERSHOP_HOSTS = {"computershopperu.com", "www.computershopperu.com"}


class ComputerShopAdapter(BaseStoreAdapter):
    """Scraping adapter for Computer Shop Perú (PrestaShop e-commerce)."""

    def __init__(self, http_client: SafeHttpClient | None = None) -> None:
        self.client = http_client or SafeHttpClient(allowed_hosts=ALLOWED_COMPUTERSHOP_HOSTS)

    def fetch_product_price(self, store_product_url: str) -> ScrapedPriceResult:
        """Fetch and extract structured product data from Computer Shop product URL."""
        response = self.client.get(store_product_url)
        return self.parse_html(response.text, store_product_url)

    def parse_html(self, html_content: str, source_url: str) -> ScrapedPriceResult:
        """Parse raw HTML content into normalized ScrapedPriceResult."""
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Title / Name
        name = self._extract_name(soup)

        # 2. Raw MPN (preserve faithfully without altering punctuation)
        raw_mpn = self._extract_raw_mpn(soup, name, source_url)

        # 3. SKU / Reference
        sku = self._extract_sku(soup)

        # 4. Availability (in_stock, out_of_stock, unknown)
        availability = self._extract_availability(soup)

        # 5. Price in PEN
        price, currency = self._extract_price(soup, availability)

        if availability == "unknown" and price is not None:
            logger.warning(
                "Product %s has 'unknown' availability with price %s %s. "
                "Preserving value for audit, excluded from lowest price / offers.",
                source_url,
                price,
                currency,
            )

        # 6. Image URL (URL string only, no CDN downloading)
        image_url = self._extract_image_url(soup)

        if not name and not sku and price is None:
            raise FatalScrapingError(
                f"Missing required product fields in Computer Shop page: {source_url}"
            )

        return ScrapedPriceResult(
            price=price,
            currency=currency,
            availability=availability,
            price_condition="cash_or_bank_transfer",
            captured_at=datetime.now(timezone.utc),
            sku=sku,
            mpn=raw_mpn,
            raw_mpn=raw_mpn,
            name=name,
            image_url=image_url,
        )

    def _extract_name(self, soup: BeautifulSoup) -> str | None:
        """Extract product name from h1 or meta tags."""
        h1_el = soup.find("h1", class_=re.compile(r"product|page-title|h1", re.I)) or soup.find(
            "h1"
        )
        if h1_el:
            text = h1_el.get_text(strip=True)
            if text:
                return text

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        return None

    def _extract_raw_mpn(
        self, soup: BeautifulSoup, name: str | None, source_url: str
    ) -> str | None:
        """Extract exact manufacturer part number without altering punctuation."""
        # 1. Search in title for "(PN:...)"
        search_text = name or ""
        if not search_text:
            h1_el = soup.find("h1")
            search_text = h1_el.get_text(strip=True) if h1_el else ""

        pn_match = re.search(r"\(PN:\s*([^\)]+)\)", search_text, re.IGNORECASE)
        if pn_match:
            raw = pn_match.group(1).strip()
            if raw:
                return raw

        # 2. Fallback: check URL slug for "-pn<mpn>.html"
        url_match = re.search(r"-pn([a-zA-Z0-9\-_']+)\.html", source_url, re.IGNORECASE)
        if url_match:
            return url_match.group(1).strip()

        return None

    def _extract_sku(self, soup: BeautifulSoup) -> str | None:
        """Extract product reference/SKU from PrestaShop reference container."""
        ref_el = soup.find(class_=re.compile(r"product-reference|reference", re.I))
        if not ref_el:
            return None

        # May contain <span class="editable">114026001</span> or text "Referencia 114026001"
        editable = ref_el.find(class_=re.compile(r"editable|value", re.I))
        if editable and editable.get_text(strip=True):
            return editable.get_text(strip=True)

        full_text = ref_el.get_text(strip=True)
        cleaned = re.sub(r"^Referencia\s*:?", "", full_text, flags=re.IGNORECASE).strip()
        return cleaned or None

    def _extract_availability(self, soup: BeautifulSoup) -> Availability:
        """Determine product availability: 'in_stock', 'out_of_stock', or 'unknown'."""
        # Check stock containers
        containers = []
        feat_sec = soup.find(class_=re.compile(r"product-features|data-sheet", re.I))
        if feat_sec:
            containers.append(feat_sec.get_text(" ", strip=True))

        avail_el = soup.find(id=re.compile(r"product-availability", re.I)) or soup.find(
            class_=re.compile(r"product-availability|availability", re.I)
        )
        if avail_el:
            containers.append(avail_el.get_text(" ", strip=True))

        combined_text = " ".join(containers).lower()

        # 1. Check for explicit 0 units or Out of Stock
        if re.search(r"en stock\s+0\s+art", combined_text) or "agotado" in combined_text:
            return "out_of_stock"

        # 2. Check for explicit positive units in stock
        if re.search(r"en stock\s+[1-9]\d*\s+art", combined_text) or (
            "en stock" in combined_text and "0 art" not in combined_text
        ):
            return "in_stock"

        # 3. Check for ambiguous 'consultar disponibilidad'
        if "consultar disponibilidad" in combined_text or "disponibilidad" in combined_text:
            return "unknown"

        # If no stock information is found
        return "unknown"

    def _extract_price(
        self, soup: BeautifulSoup, availability: Availability
    ) -> tuple[Decimal | None, str | None]:
        """Extract base_price (condition: cash_or_bank_transfer) in PEN.

        Computer Shop publishes a base_price for cash or bank transfer (*Sin recargo por
        pago en Efectivo o Transferencia) and a credit card price with 5% surcharge.
        Only base_price is tracked; card surcharge is ignored and never stored as a 2nd observation.
        """
        # 1. Look for .current-price elements that do not represent card surcharge
        candidates = soup.find_all(class_=re.compile(r"\bcurrent-price\b", re.I))
        price_el = None
        for cand in candidates:
            cand_text = cand.get_text(" ", strip=True)
            if not re.search(r"tarjeta|con\s+recargo", cand_text, re.IGNORECASE):
                price_el = cand
                break
        if not price_el and candidates:
            price_el = candidates[0]

        # 2. Fallback: check other price containers, excluding card surcharge elements
        if not price_el:
            fallback_els = soup.find_all(
                ["div", "span"], class_=re.compile(r"product-price|price", re.I)
            )
            for el in fallback_els:
                el_text = el.get_text(" ", strip=True)
                if not re.search(r"tarjeta|con\s+recargo", el_text, re.IGNORECASE) and re.search(
                    r"(?:S\/?\.?|PEN)", el_text, re.IGNORECASE
                ):
                    price_el = el
                    break

        if not price_el:
            if availability in ("out_of_stock", "unknown"):
                return None, None
            raise FatalScrapingError("Missing price for in_stock product on Computer Shop")

        price_text = price_el.get_text(" ", strip=True)

        # If a card surcharge section is bundled in the same text, strip it out
        match_surcharge = re.search(r"\*?\s*(?:con\s+recargo|tarjeta)", price_text, re.IGNORECASE)
        if match_surcharge:
            prefix = price_text[: match_surcharge.start()].strip()
            if re.search(r"(?:S\/?\.?|PEN)", prefix, re.IGNORECASE):
                price_text = prefix

        try:
            parsed_pen = parse_pen_price(price_text)
            return parsed_pen, "PEN"
        except FatalScrapingError:
            # If product is out of stock or unknown and price text has no PEN, allow price=None
            if availability in ("out_of_stock", "unknown") and not re.search(
                r"(?:S\/?\.?|PEN)", price_text, re.IGNORECASE
            ):
                return None, None
            raise

    def _extract_image_url(self, soup: BeautifulSoup) -> str | None:
        """Extract canonical product image URL without downloading image."""
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            url = og_img["content"].strip()
            if url.startswith("http"):
                return url

        img_el = soup.find("img", class_=re.compile(r"js-qv-product-cover|product-image", re.I))
        if img_el:
            url = img_el.get("src") or img_el.get("data-image-large-src")
            if url and url.startswith("http"):
                return url.strip()

        return None
