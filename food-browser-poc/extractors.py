"""
extractors.py — Platform-specific data extraction logic.
Selectors calibrated from live DOM inspection (2026-09-21).

Each extractor receives a BrowserSession and returns:
- list of restaurant dicts
- list of dish dicts for menu extraction
"""

from __future__ import annotations

import re
from typing import Optional

from browser import BrowserSession

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_price(text: str) -> Optional[int]:
    """Extract the first number from a Vietnamese price string, e.g. '65.000đ' → 65000."""
    if not text:
        return None
    # If string contains multiple numbers (e.g. '85.000đ\n83.300đ'), find all matches
    # Clean separators like '.' and 'đ'
    matches = re.findall(r"(\d[\d\.,]*)", text)
    if not matches:
        return None
    # Return the first or last depending on context; generally take the last if discounted
    # but for simple single price:
    clean = re.sub(r"[^\d]", "", matches[-1])
    return int(clean) if clean else None


def _parse_first_price(text: str) -> Optional[int]:
    """Extract the very first price number from a string."""
    if not text:
        return None
    matches = re.findall(r"(\d[\d\.,]*)", text)
    if not matches:
        return None
    clean = re.sub(r"[^\d]", "", matches[0])
    return int(clean) if clean else None


def _parse_rating(text: str) -> Optional[float]:
    m = re.search(r"(\d+[.,]\d+)", text)
    if m:
        return float(m.group(1).replace(",", "."))
    m2 = re.search(r"^(\d)$", text.strip())
    if m2:
        val = int(m2.group(1))
        return float(val) if val <= 5 else None
    return None


def _empty_restaurant(platform: str) -> dict:
    return {
        "platform": platform,
        "restaurant_name": None,
        "address": None,
        "rating": None,
        "category": None,
        "dish_name": None,
        "dish_price": None,
        "promotion": None,
        "restaurant_url": None,
        "menu": [],
    }


def _extract_schema_org_address(b: BrowserSession) -> Optional[str]:
    """Extract street address from JSON-LD schema (present on both GrabFood & ShopeeFood)."""
    try:
        data = b.page.evaluate("""() => {
            const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
            for (const s of scripts) {
                try {
                    const json = JSON.parse(s.innerText);
                    const items = Array.isArray(json) ? json : [json];
                    for (const item of items) {
                        if (item.address) {
                            if (typeof item.address === 'string') return item.address;
                            if (typeof item.address === 'object') {
                                const parts = [
                                    item.address.streetAddress,
                                    item.address.addressLocality,
                                    item.address.addressRegion,
                                ].filter(Boolean);
                                return parts.join(', ');
                            }
                        }
                    }
                } catch(e) {}
            }
            return null;
        }""")
        return data
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ShopeeFood extractor
# ---------------------------------------------------------------------------

class ShopeeFoodExtractor:
    PLATFORM = "ShopeeFood"
    BASE_URL = "https://shopeefood.vn"

    # Primary card selector
    _CARD_SEL = "div.list-restaurant-item-wrapper"
    # Fallbacks for category/food listing
    _CARD_FALLBACKS = [
        "div.item-restaurant",
        "div[class*='item-restaurant']",
        "div[class*='list-restaurant-item']",
        "div[class*='restaurant-item']",
    ]

    def __init__(self, session: BrowserSession):
        self.b = session

    def extract_cards(self, max_count: int = 10) -> list[dict]:
        """Find and parse visible restaurant card wrappers on the current page."""
        cards_el = self._find_cards(self._CARD_SEL)
        if not cards_el:
            for sel in self._CARD_FALLBACKS:
                cards_el = self._find_cards(sel)
                if cards_el:
                    break

        if not cards_el:
            print("[Extractor] ShopeeFood: no restaurant cards found with known selectors.")
            return []

        results = []
        seen_names = set()
        for el in cards_el:
            if len(results) >= max_count:
                break
            r = self._parse_card(el)
            name = r.get("restaurant_name")
            if name and name in seen_names:
                continue
            if name:
                seen_names.add(name)
            results.append(r)
        return results

    def _find_cards(self, selector: str) -> list:
        els = self.b.query_elements(selector)
        visible = [e for e in els if self._is_visible(e)]
        if visible:
            print(f"[Extractor] ShopeeFood: found {len(visible)} card(s) with '{selector}'")
        return visible

    def _parse_card(self, el) -> dict:
        r = _empty_restaurant(self.PLATFORM)

        # --- name ---
        name = (
            self._text(el, ".list-restaurant-item-body-info-name-text")
            or self._text(el, ".list-restaurant-name")
            or self._text(el, ".item-restaurant-name")
            or self._text(el, "h3")
            or self._text(el, "h2")
        )
        if not name:
            try:
                first_line = el.inner_text().strip().splitlines()[0]
                if first_line and len(first_line) > 2 and "đăng nhập" not in first_line.lower():
                    name = first_line
            except Exception:
                pass
        r["restaurant_name"] = name or None

        # --- rating ---
        rating_text = self._text(el, ".list-restaurant-item-body-info-detail-rating")
        if rating_text:
            r["rating"] = _parse_rating(rating_text)

        # --- promotion ---
        promo = (
            self._text(el, ".list-restaurant-item-body-promotion-description")
            or self._text(el, ".list-restaurant-item-body-photo-promo-label-text")
            or self._text(el, ".icon-price-tag")
            or self._text(el, "[class*='promo']")
        )
        r["promotion"] = promo or None

        # --- category ---
        category = self._text(el, ".list-restaurant-info-badge-category") or self._text(el, ".item-restaurant-category")
        r["category"] = category or None

        # --- address ---
        addr = (
            self._text(el, ".address-res")
            or self._text(el, ".item-restaurant-address")
            or self._text(el, "[class*='address']")
        )
        r["address"] = addr or None

        # --- URL ---
        try:
            link = el.query_selector("a.list-restaurant-item-body")
            if not link:
                link = el.query_selector("a[href*='/ha-noi/']")
            if not link:
                link = el.query_selector("a[href]")
            if not link and el.evaluate("el => el.tagName") == "A":
                link = el
            if link:
                href = link.get_attribute("href") or ""
                if href:
                    r["restaurant_url"] = href if href.startswith("http") else f"{self.BASE_URL}{href}"
        except Exception:
            pass

        return r

    def extract_menu(self, max_dishes: int = 30) -> list[dict]:
        """Extract dishes and prices from the current ShopeeFood restaurant page."""
        dishes = []
        dish_row_selectors = [
            ".item-restaurant-row",
            "[class*='item-restaurant-row']",
            ".row-item-restaurant",
        ]

        items_el = []
        for sel in dish_row_selectors:
            els = self.b.query_elements(sel)
            visible = [e for e in els if self._is_visible(e)]
            if visible:
                items_el = visible
                print(f"[Extractor] ShopeeFood: found {len(visible)} dish row(s) with '{sel}'")
                break

        seen_names = set()
        for el in items_el:
            if len(dishes) >= max_dishes:
                break

            name_el = el.query_selector(".item-restaurant-name, h2, h3, [class*='name']")
            if not name_el:
                continue
            name_text = name_el.inner_text().strip()
            dish_name = name_text.split("\n")[0].strip()
            if not dish_name or dish_name in seen_names:
                continue
            seen_names.add(dish_name)

            desc_el = el.query_selector(".item-restaurant-desc, [class*='desc']")
            desc_text = desc_el.inner_text().strip() if desc_el else None

            # Current and old price
            price_el = el.query_selector(".current-price, .product-price, [class*='price']")
            price_text = price_el.inner_text().strip() if price_el else ""
            lines = [ln.strip() for ln in price_text.splitlines() if ln.strip()]

            dish_price = None
            orig_price = None
            if len(lines) >= 2:
                orig_price = _parse_first_price(lines[0])
                dish_price = _parse_price(lines[-1])
            elif len(lines) == 1:
                dish_price = _parse_price(lines[0])

            old_price_el = el.query_selector(".old-price")
            if old_price_el and not orig_price:
                orig_price = _parse_price(old_price_el.inner_text().strip())

            discount_text = None
            if orig_price and dish_price and orig_price > dish_price:
                diff = orig_price - dish_price
                pct = int(round(diff / orig_price * 100))
                discount_text = f"Giảm {pct}% (-{diff:,}đ)"

            if dish_name and dish_price:
                dishes.append({
                    "dish_name": dish_name,
                    "dish_price": dish_price,
                    "original_price": orig_price,
                    "description": desc_text,
                    "discount": discount_text,
                })

        return dishes

    def _text(self, el, selector: str) -> Optional[str]:
        try:
            child = el.query_selector(selector)
            if child and child.is_visible():
                return child.inner_text().strip() or None
        except Exception:
            pass
        return None

    def _is_visible(self, el) -> bool:
        try:
            return el.is_visible()
        except Exception:
            return False


# ---------------------------------------------------------------------------
# GrabFood extractor
# ---------------------------------------------------------------------------

class GrabFoodExtractor:
    PLATFORM = "GrabFood"
    BASE_URL = "https://food.grab.com"

    # Primary: restaurant links (each card is an <a> with restaurant URL)
    _CARD_CANDIDATES = [
        "a[href*='/vn/en/restaurant/']",
        "[class*='restaurantContainer']",
        "div[class*='restaurantCard']",
        "div[class*='merchantCard']",
        "div[class*='restaurant-card']",
    ]

    def __init__(self, session: BrowserSession):
        self.b = session

    def extract_cards(self, max_count: int = 10) -> list[dict]:
        cards_el = []

        for sel in self._CARD_CANDIDATES:
            els = self.b.query_elements(sel)
            visible = [e for e in els if self._is_visible(e)]
            if len(visible) >= 2:
                cards_el = visible
                print(f"[Extractor] GrabFood: found {len(visible)} card(s) with '{sel}'")
                break

        if not cards_el:
            print("[Extractor] GrabFood: no restaurant cards found with known selectors.")
            return []

        results = []
        seen_names: set[str] = set()
        for el in cards_el:
            if len(results) >= max_count:
                break
            r = self._parse_card(el)
            name = r.get("restaurant_name")
            if name and name in seen_names:
                continue
            if name:
                seen_names.add(name)
            results.append(r)

        return results

    def _parse_card(self, el) -> dict:
        r = _empty_restaurant(self.PLATFORM)

        try:
            full_text = el.inner_text().strip()
        except Exception:
            full_text = ""

        # --- name ---
        lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
        if lines:
            name_line = lines[0] if lines[0].lower() != "promo" else (lines[1] if len(lines) > 1 else None)
            r["restaurant_name"] = name_line

        # --- category ---
        if len(lines) >= 2:
            second = lines[1] if lines[1].lower() != "promo" else (lines[2] if len(lines) > 2 else None)
            if second and not re.search(r"^\d|mins|km", second):
                r["category"] = second

        # --- rating ---
        for ln in lines:
            val = _parse_rating(ln)
            if val and val <= 5.0:
                r["rating"] = val
                break

        # --- promotion ---
        promo_text = (
            self._text(el, "[class*='promoTag']")
            or self._text(el, "[class*='discountText']")
            or self._text(el, "[class*='vendorTag']")
        )
        if not promo_text and "promo" in full_text.lower():
            promo_text = "Promo"
        r["promotion"] = promo_text or None

        # --- URL ---
        try:
            href = el.get_attribute("href")
            if not href:
                link = el.query_selector("a[href*='/restaurant/']")
                if not link:
                    link = el.query_selector("a[href]")
                if link:
                    href = link.get_attribute("href") or ""
            if href:
                r["restaurant_url"] = href if href.startswith("http") else f"{self.BASE_URL}{href}"
        except Exception:
            pass

        return r

    def extract_menu(self, max_dishes: int = 30) -> list[dict]:
        """Extract dishes and prices from the current GrabFood restaurant page."""
        dishes = []
        dish_selectors = [
            "[class*='menuItem___']",
            "[class*='menuItemWrapper']",
        ]
        items_el = []
        for sel in dish_selectors:
            els = self.b.query_elements(sel)
            visible = [e for e in els if self._is_visible(e)]
            if visible:
                items_el = visible
                print(f"[Extractor] GrabFood: found {len(visible)} dish elements with '{sel}'")
                break

        seen_names = set()
        for el in items_el:
            if len(dishes) >= max_dishes:
                break

            name_el = el.query_selector("[class*='itemNameTitle'], [class*='itemName']")
            if not name_el:
                continue
            name_text = name_el.inner_text().strip()
            dish_name = name_text.split("\n")[0].strip()
            if not dish_name or dish_name in seen_names:
                continue
            seen_names.add(dish_name)

            desc_el = el.query_selector("[class*='itemDescription']")
            desc_text = desc_el.inner_text().strip() if desc_el else None

            # Current price
            price_el = el.query_selector("[class*='discountedPrice'], [class*='itemPrice']")
            price_text = price_el.inner_text().strip() if price_el else ""
            dish_price = _parse_price(price_text)

            # Original price
            orig_price_el = el.query_selector("[class*='originPrice']")
            orig_price_text = orig_price_el.inner_text().strip() if orig_price_el else ""
            orig_price = _parse_price(orig_price_text)

            # Discount tag
            discount_el = el.query_selector("[class*='itemDiscount']")
            discount_text = discount_el.inner_text().strip() if discount_el else None
            if discount_text:
                discount_text = discount_text.split("\n")[0].strip()

            if dish_name and dish_price:
                dishes.append({
                    "dish_name": dish_name,
                    "dish_price": dish_price,
                    "original_price": orig_price,
                    "description": desc_text,
                    "discount": discount_text,
                })

        return dishes

    def _text(self, el, selector: str) -> Optional[str]:
        try:
            child = el.query_selector(selector)
            if child and child.is_visible():
                return child.inner_text().strip() or None
        except Exception:
            pass
        return None

    def _is_visible(self, el) -> bool:
        try:
            return el.is_visible()
        except Exception:
            return False
