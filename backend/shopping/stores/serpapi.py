"""SerpApi Google Shopping provider with strict INR price validation.

The API key is read only on the backend from SERPAPI_API_KEY. Products are
cached in memory by stable internal ID so subsequent MCP get_product calls can
resolve the exact search result without fabricating data.
"""
from __future__ import annotations

import hashlib
import logging
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

from backend.shopping.product_normalizer import Product
from backend.shopping.stores.base_store import BaseStore

load_dotenv()
logger = logging.getLogger(__name__)
SERPAPI_URL = "https://serpapi.com/search.json"
DEFAULT_TIMEOUT_SECONDS = 8.0
SEARCH_CACHE_TTL_SECONDS = 600

_INR_MARKERS = ("₹", "INR", "RS.", "RS ", "RUPEE", "RUPEES")
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d{1,2})?")


def _is_inr_price_text(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    upper = value.upper()
    return any(marker in upper for marker in _INR_MARKERS)


def _safe_inr_price(result: Dict[str, Any]) -> Optional[float]:
    """Return a price only when the result explicitly identifies INR."""
    text = result.get("price")
    explicit_currency = str(result.get("currency") or "").strip().upper()
    if isinstance(text, str) and any(
    marker in text.upper()
    for marker in ("$", "£", "€", "USD", "EUR", "GBP")):
        return None
    if explicit_currency != "INR" and not _is_inr_price_text(text):
        return None

    numbers = _NUMBER_RE.findall(text) if isinstance(text, str) else []
    # A displayed range is ambiguous even if SerpApi also supplies extracted_price.
    if len(numbers) > 1:
        return None

    extracted = result.get("extracted_price")
    if extracted is not None:
        if isinstance(extracted, bool):
            return None
        try:
            price = float(str(extracted).replace(",", ""))
        except (TypeError, ValueError):
            price = None
        if price is not None:
            return price if price >= 0 else None

    if not isinstance(text, str):
        return None
    # A single explicitly INR-denominated display price can be parsed safely.
    numbers = _NUMBER_RE.findall(text)
    if len(numbers) != 1:
        return None
    try:
        price = float(numbers[0].replace(",", ""))
    except ValueError:
        return None
    return price if price >= 0 else None


def _valid_http_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _stable_id(result: Dict[str, Any], product_url: str, title: str, merchant: str) -> str:
    provider_id = result.get("product_id")
    # Include listing URL and merchant so same-Google-product offers from
    # different retailers remain distinct while each listing ID stays stable.
    identity = f"{provider_id}|{product_url}|{merchant}" if provider_id else f"{product_url}|{merchant}|{title}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"serp_{digest}"


class SerpApiStore(BaseStore):
    """Google Shopping search via SerpApi; no direct browser/frontend calls."""

    def __init__(self, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds
        self._products: Dict[str, Product] = {}
        # Cache successful searches to avoid repeating identical paid requests.
        self._search_cache: Dict[str, tuple[float, List[Product]]] = {}

    def _api_key(self) -> str:
        # Read dynamically to support dotenv/environment configuration without logging it.
        return (os.getenv("SERPAPI_API_KEY") or "").strip()

    def _market(self) -> tuple[str, str, str]:
        country = (os.getenv("DEFAULT_COUNTRY") or "India").strip()
        country_codes = {
            "india": "in", "in": "in", "ind": "in",
            "united states": "us", "usa": "us", "us": "us",
            "united kingdom": "uk", "uk": "uk", "gb": "uk",
            "canada": "ca", "ca": "ca", "australia": "au", "au": "au",
            "singapore": "sg", "sg": "sg", "united arab emirates": "ae", "ae": "ae",
        }
        gl = (os.getenv("SERPAPI_GL") or country_codes.get(country.lower(), "us")).lower()
        hl = (os.getenv("SERPAPI_HL") or "en").lower()
        location = (os.getenv("SERPAPI_LOCATION") or country).strip()
        return gl, hl, location

    def _build_query(
        self, query: str, category: Optional[str], color: Optional[str], budget: Optional[float],
        occasion: Optional[str] = None, style: Optional[str] = None,
    ) -> str:
        parts: list[str] = []
        for part in (query, category, color, occasion, style):
            clean = str(part or "").strip()
            if clean and clean.lower() not in " ".join(parts).lower():
                parts.append(clean)
        if budget is not None and budget > 0:
            parts.append(f"under ₹{budget:g}")
        return " ".join(parts) or "clothing"

    def search_products(
        self,
        query: str,
        budget: Optional[float] = None,
        category: Optional[str] = None,
        color: Optional[str] = None,
        occasion: Optional[str] = None,
        style: Optional[str] = None,
    ) -> List[Product]:
        api_key = self._api_key()
        if not api_key:
            raise RuntimeError("SERPAPI_API_KEY is not configured")
        gl, hl, location = self._market()
        params = {
            "engine": "google_shopping",
            "q": self._build_query(query, category, color, budget, occasion, style),
            "api_key": api_key,
            "gl": gl,
            "hl": hl,
            "location": location,
        }

        # Exclude the API key from the cache key.
        cache_material = json.dumps(
            {key: value for key, value in params.items() if key != "api_key"},
            sort_keys=True,
            separators=(",", ":"),
        )
        cache_key = hashlib.sha256(cache_material.encode("utf-8")).hexdigest()
        now = time.monotonic()
        cached = self._search_cache.get(cache_key)
        if cached and now - cached[0] < SEARCH_CACHE_TTL_SECONDS:
            logger.info("serpapi_cache=hit")
            return list(cached[1])
        if cached:
            self._search_cache.pop(cache_key, None)

        try:
            response = httpx.get(SERPAPI_URL, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("SerpApi Google Shopping request timed out") from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SerpApi Google Shopping request failed ({type(exc).__name__})") from exc
        except ValueError as exc:
            raise RuntimeError("SerpApi returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("SerpApi returned an unexpected response")
        if payload.get("error"):
            # Avoid echoing the full payload: it can include request metadata.
            raise RuntimeError("SerpApi reported an API error")
        rows = payload.get("shopping_results")
        if not isinstance(rows, list):
            rows = []

        products: List[Product] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip()
            merchant = str(row.get("source") or row.get("merchant") or "Unknown merchant").strip()
            product_url = _valid_http_url(row.get("product_link")) or _valid_http_url(row.get("link"))
            image_url = _valid_http_url(row.get("thumbnail"))
            price = _safe_inr_price(row)
            if not title or not product_url or price is None:
                continue
            if budget is not None and price > budget:
                continue
            product_id = _stable_id(row, product_url, title, merchant)
            product = Product(
                product_id=product_id,
                store=f"SerpApi / {merchant}",
                brand=str(row.get("brand") or merchant),
                title=title,
                category=(str(category).strip().lower() if category else "uncategorized"),
                color=(str(row.get("color")).strip().lower() if row.get("color") else None),
                price=price,
                currency="INR",
                sizes=[],
                image_url=image_url,
                product_url=product_url,
                # Google Shopping listing is not a guarantee of size-level stock.
                availability=True,
            )
            self._products[product_id] = product
            products.append(product)

        # Cache even an empty successful result briefly, preventing immediate
        # duplicate paid requests for the same query.
        self._search_cache[cache_key] = (time.monotonic(), list(products))
        logger.info("serpapi_cache=miss result_count=%d", len(products))
        return products

    def get_product(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)

    def get_variants(self, product_id: str) -> List[Product]:
        return []

    def check_availability(self, product_id: str) -> bool:
        # Listing presence only; no size-level inventory is available from this adapter.
        return product_id in self._products

    def get_alternatives(self, product_id: str, limit: int = 5) -> List[Product]:
        product = self._products.get(product_id)
        if not product:
            return []
        return [p for p in self._products.values() if p.product_id != product_id and p.category == product.category][:max(0, limit)]
