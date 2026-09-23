"""
agent.py — Minimal agent layer with Menu & Price extraction.

The agent receives (platform, location, request) and translates them into
an ordered sequence of browser tool calls.

Key features:
- Searches & extracts restaurant cards
- Visits restaurant detail pages to extract menu dishes & prices
- Returns structured PlatformResult
"""
from __future__ import annotations

import sys
# Ensure stdout/stderr handle UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from browser import BrowserSession
from extractors import ShopeeFoodExtractor, GrabFoodExtractor

RESULTS_DIR = Path(__file__).parent / "artifacts" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------

@dataclass
class PlatformResult:
    platform: str
    website_accessible: bool = False
    browser_interaction: bool = False
    search_possible: bool = False
    restaurant_cards_readable: bool = False
    restaurant_detail_readable: bool = False
    menu_readable: bool = False
    promotion_readable: bool = False
    blocked_by: Optional[str] = None
    restaurants: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def add_note(self, msg: str):
        print(f"[Agent] NOTE: {msg}")
        self.notes.append(msg)


# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

SHOPEEFOOD_URL = "https://shopeefood.vn"
GRABFOOD_URL = "https://food.grab.com/vn/en/"


class FoodAgent:
    def __init__(
        self,
        location: str,
        user_request: str,
        headless: bool = False,
        extract_menu: bool = True,
    ):
        self.location = location          # e.g. "Cầu Giấy, Hà Nội"
        self.user_request = user_request  # e.g. "Tìm đồ ăn cay"
        self.district = location.split(",")[0].strip()
        self.city = location.split(",")[-1].strip() if "," in location else "Hà Nội"
        self.headless = headless
        self.extract_menu = extract_menu

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    def run_shopeefood(self) -> PlatformResult:
        result = PlatformResult(platform="ShopeeFood")
        session = BrowserSession(headless=self.headless)

        try:
            session.start()
            self._run_shopeefood_flow(session, result)
        except Exception as exc:
            result.add_note(f"Unhandled exception: {exc}")
            result.blocked_by = f"EXCEPTION: {exc}"
        finally:
            try:
                session.take_screenshot("shopeefood_final")
            except Exception:
                pass
            session.close()

        # Persist JSON
        self._save_json(result, "shopeefood.json")
        return result

    def run_grabfood(self) -> PlatformResult:
        result = PlatformResult(platform="GrabFood")
        session = BrowserSession(headless=self.headless)

        try:
            session.start()
            self._run_grabfood_flow(session, result)
        except Exception as exc:
            result.add_note(f"Unhandled exception: {exc}")
            result.blocked_by = f"EXCEPTION: {exc}"
        finally:
            try:
                session.take_screenshot("grabfood_final")
            except Exception:
                pass
            session.close()

        self._save_json(result, "grabfood.json")
        return result

    # ------------------------------------------------------------------
    # ShopeeFood flow implementation
    # ------------------------------------------------------------------

    def _run_shopeefood_flow(self, b: BrowserSession, result: PlatformResult):
        print("\n" + "=" * 60)
        print("[Agent] Starting ShopeeFood flow")
        print(f"[Agent] Location: {self.location}")
        print(f"[Agent] Request : {self.user_request}")
        print(f"[Agent] Extract Menu: {self.extract_menu}")
        print("=" * 60)

        # Step 1: Open home page
        print("\n[Browser] Opening ShopeeFood...")
        url = b.open_page(SHOPEEFOOD_URL, wait_until="networkidle", timeout=30_000)
        b.take_screenshot("shopeefood_home")

        page_title = b.get_title()
        print(f"[Browser] Title: {page_title}")

        if not url or "shopeefood" not in url.lower():
            result.add_note(f"Unexpected URL after load: {url}")
            result.blocked_by = "CANNOT_REACH_WEBSITE"
            return

        result.website_accessible = True
        result.browser_interaction = True
        print("[Agent] ShopeeFood home page reached ✓")

        b.wait(1500)
        b.dismiss_common_popups()
        b.wait(1000)

        # Step 2: Navigate to discovery page
        print("\n[Browser] Navigating to Hà Nội food discovery...")
        discovery_url = f"https://shopeefood.vn/ha-noi/danh-sach-dia-diem?q={self.district}"
        b.open_page(discovery_url, wait_until="networkidle", timeout=30_000)
        b.wait(2000)
        b.dismiss_common_popups()
        result.search_possible = True

        # Scroll to load cards
        print("[Browser] Scrolling to load results...")
        for _ in range(3):
            b.scroll("down", 700)
            b.wait(1000)
        b.take_screenshot("shopeefood_after_scroll")

        # Step 3: Extract restaurant cards
        print("\n[Browser] Extracting restaurant cards...")
        extractor = ShopeeFoodExtractor(b)
        restaurants = extractor.extract_cards(max_count=10)

        # If empty (due to session quirks on search URL), fallback to category page
        if not restaurants:
            print("[Browser] Search listing yielded 0 cards, falling back to /ha-noi/food...")
            fallback_url = "https://shopeefood.vn/ha-noi/food"
            b.open_page(fallback_url, wait_until="networkidle", timeout=30_000)
            b.wait(2000)
            for _ in range(2):
                b.scroll("down", 600)
                b.wait(800)
            restaurants = extractor.extract_cards(max_count=10)

        if restaurants:
            result.restaurant_cards_readable = True
            result.restaurants = restaurants
            result.promotion_readable = any(r.get("promotion") for r in restaurants)
            print(f"[Browser] Found {len(restaurants)} restaurant card(s)")
            for i, r in enumerate(restaurants, 1):
                print(f"  [{i}] {r['restaurant_name']} | rating={r['rating']} | url={r.get('restaurant_url')}")
        else:
            print("[Browser] No restaurant cards extracted.")
            result.add_note("No restaurant cards found. Site may use unknown selectors or require login.")

        # Step 4: Extract Menu for top restaurant
        if self.extract_menu and restaurants:
            target_rest = next((r for r in restaurants if r.get("restaurant_url")), None)
            if target_rest:
                target_url = target_rest["restaurant_url"]
                print(f"\n[Agent] Navigating to restaurant detail page: {target_url}")
                b.open_page(target_url, wait_until="networkidle", timeout=30_000)
                b.wait(2500)
                b.scroll("down", 500)
                b.wait(1000)
                b.take_screenshot("shopeefood_restaurant_menu")

                menu = extractor.extract_menu(max_dishes=25)
                if not target_rest.get("address"):
                    from extractors import _extract_schema_org_address
                    addr = _extract_schema_org_address(b)
                    if addr:
                        target_rest["address"] = addr
                        print(f"[Extractor] ShopeeFood: extracted address: {addr}")
                if menu:
                    result.restaurant_detail_readable = True
                    result.menu_readable = True
                    target_rest["menu"] = menu
                    target_rest["dish_name"] = menu[0]["dish_name"]
                    target_rest["dish_price"] = menu[0]["dish_price"]
                    print(f"[Extractor] ShopeeFood: successfully extracted {len(menu)} dish(es)!")
                    for idx, d in enumerate(menu[:5], 1):
                        orig_str = f" (gốc {d['original_price']:,}đ)" if d.get('original_price') else ""
                        disc_str = f" [{d['discount']}]" if d.get('discount') else ""
                        print(f"  [{idx}] {d['dish_name']} — {d['dish_price']:,}đ{orig_str}{disc_str}")
                else:
                    print("[Extractor] ShopeeFood: could not extract dishes from detail page.")

        # Step 5: Diagnostics
        visible = b.extract_visible_content(max_chars=1000)
        if "access denied" in visible.lower() or "403" in visible or "cloudflare" in visible.lower():
            result.blocked_by = "ACCESS_DENIED / CLOUDFLARE"
        elif not restaurants and "đăng nhập" in visible.lower():
            result.blocked_by = "LOGIN_REQUIRED"

    # ------------------------------------------------------------------
    # GrabFood flow implementation
    # ------------------------------------------------------------------

    def _run_grabfood_flow(self, b: BrowserSession, result: PlatformResult):
        print("\n" + "=" * 60)
        print("[Agent] Starting GrabFood flow")
        print(f"[Agent] Location: {self.location}")
        print(f"[Agent] Request : {self.user_request}")
        print(f"[Agent] Extract Menu: {self.extract_menu}")
        print("=" * 60)

        # Step 1: Open GrabFood
        print("\n[Browser] Opening GrabFood...")
        url = b.open_page(GRABFOOD_URL, wait_until="networkidle", timeout=30_000)
        b.take_screenshot("grabfood_home")

        page_title = b.get_title()
        print(f"[Browser] Title: {page_title}")

        if "grab" not in url.lower() and "grab" not in page_title.lower():
            result.add_note(f"Unexpected URL/title: {url} / {page_title}")
            result.blocked_by = "CANNOT_REACH_WEBSITE"
            return

        result.website_accessible = True
        result.browser_interaction = True
        print("[Agent] GrabFood home page reached ✓")

        # Step 2: Dismiss popups
        b.wait(2000)
        b.dismiss_common_popups()
        b.wait(1000)

        # Step 3: Location setting
        print(f"\n[Browser] Setting location to '{self.location}'...")
        self._grabfood_set_location(b, result)
        b.take_screenshot("grabfood_after_location")

        # Step 4: Scroll and wait for results
        print("[Browser] Waiting for restaurant list to load...")
        b.wait(2500)
        for _ in range(3):
            b.scroll("down", 700)
            b.wait(1000)

        b.take_screenshot("grabfood_search")

        # Step 5: Extract restaurant cards
        print("\n[Browser] Extracting restaurant cards...")
        extractor = GrabFoodExtractor(b)
        restaurants = extractor.extract_cards(max_count=10)

        if restaurants:
            result.restaurant_cards_readable = True
            result.restaurants = restaurants
            result.promotion_readable = any(r.get("promotion") for r in restaurants)
            print(f"[Browser] Found {len(restaurants)} restaurant card(s)")
            for i, r in enumerate(restaurants, 1):
                print(f"  [{i}] {r['restaurant_name']} | rating={r['rating']} | promo={r['promotion']}")
        else:
            print("[Browser] No restaurant cards extracted.")
            result.add_note("No restaurant cards found. Site may use unknown selectors or require further interaction.")

        # Step 6: Extract Menu for top restaurant
        if self.extract_menu and restaurants:
            target_rest = next((r for r in restaurants if r.get("restaurant_url")), None)
            if target_rest:
                target_url = target_rest["restaurant_url"]
                print(f"\n[Agent] Navigating to restaurant detail page: {target_url}")
                b.open_page(target_url, wait_until="networkidle", timeout=30_000)
                b.wait(2500)
                b.scroll("down", 600)
                b.wait(1000)
                b.take_screenshot("grabfood_restaurant_menu")

                menu = extractor.extract_menu(max_dishes=25)
                if not target_rest.get("address"):
                    from extractors import _extract_schema_org_address
                    addr = _extract_schema_org_address(b)
                    if addr:
                        target_rest["address"] = addr
                        print(f"[Extractor] GrabFood: extracted address: {addr}")
                if menu:
                    result.restaurant_detail_readable = True
                    result.menu_readable = True
                    target_rest["menu"] = menu
                    target_rest["dish_name"] = menu[0]["dish_name"]
                    target_rest["dish_price"] = menu[0]["dish_price"]
                    print(f"[Extractor] GrabFood: successfully extracted {len(menu)} dish(es)!")
                    for idx, d in enumerate(menu[:5], 1):
                        orig_str = f" (gốc {d['original_price']:,}đ)" if d.get('original_price') else ""
                        disc_str = f" [{d['discount']}]" if d.get('discount') else ""
                        print(f"  [{idx}] {d['dish_name']} — {d['dish_price']:,}đ{orig_str}{disc_str}")
                else:
                    print("[Extractor] GrabFood: could not extract dishes from detail page.")

        result.search_possible = True

    def _grabfood_set_location(self, b: BrowserSession, result: PlatformResult):
        location_selectors = [
            "input[placeholder*='address']",
            "input[placeholder*='Address']",
            "input[placeholder*='location']",
            "input[placeholder*='Location']",
            "input[placeholder*='địa chỉ']",
            "input[placeholder*='Địa chỉ']",
            "#location-input",
            "[data-testid='location-search-input']",
        ]

        for sel in location_selectors:
            if b.is_visible(sel):
                b.click(sel)
                b.wait(500)
                b.type_text(sel, self.district)
                b.wait(1200)

                suggestion_selectors = [
                    "[class*='suggestion']",
                    "[class*='autocomplete']",
                    "[class*='dropdown'] li",
                    "[role='listbox'] li",
                    "[role='option']",
                ]
                for sug_sel in suggestion_selectors:
                    if b.is_visible(sug_sel):
                        b.click(sug_sel)
                        b.wait(2000)
                        print(f"[Browser] Location suggestion selected via '{sug_sel}'")
                        result.add_note(f"Location set via suggestion '{sug_sel}'")
                        return

                b.press_key("Enter")
                b.wait(2000)
                print(f"[Browser] Location entered via '{sel}' (Enter pressed)")
                result.add_note(f"Location set via Enter on '{sel}'")
                return

        print("[Browser] No location input found, trying direct URL approach...")
        result.add_note("No location input selector matched; tried direct URL navigation.")
        grab_search_url = "https://food.grab.com/vn/en/restaurants"
        b.open_page(grab_search_url, wait_until="networkidle", timeout=25_000)
        b.wait(2000)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _save_json(self, result: PlatformResult, filename: str):
        output = {
            "platform": result.platform,
            "feasibility": {
                "website_accessible": result.website_accessible,
                "browser_interaction": result.browser_interaction,
                "search_possible": result.search_possible,
                "restaurant_cards_readable": result.restaurant_cards_readable,
                "restaurant_detail_readable": result.restaurant_detail_readable,
                "menu_readable": result.menu_readable,
                "promotion_readable": result.promotion_readable,
                "blocked_by": result.blocked_by,
            },
            "notes": result.notes,
            "restaurants": result.restaurants,
        }
        path = RESULTS_DIR / filename
        with open(path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"\n[Agent] Results saved → {path}")
