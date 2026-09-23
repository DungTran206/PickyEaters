"""
inspect_dom.py — Standalone script to inspect live DOM selectors on ShopeeFood and GrabFood.
Run this ONCE to discover the actual class names. Then update extractors.py accordingly.
"""
from __future__ import annotations
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
from playwright.sync_api import sync_playwright

SHOPEEFOOD_URL = "https://shopeefood.vn/ha-noi/danh-sach-dia-diem?q=Cau+Giay"
GRABFOOD_URL = "https://food.grab.com/vn/en/"

def inspect_page(pw, url: str, platform: str):
    print(f"\n{'='*60}")
    print(f"Inspecting: {platform} — {url}")
    print('='*60)

    browser = pw.chromium.launch(headless=False, slow_mo=100)
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="vi-VN",
    )
    page = ctx.new_page()
    page.goto(url, wait_until="networkidle", timeout=30_000)
    page.wait_for_timeout(3_000)

    # Screenshot
    page.screenshot(path=f"artifacts/screenshots/{platform.lower()}_dom_inspect.png")

    # Get all class names in the body
    all_classes = page.evaluate("""() => {
        const all = document.querySelectorAll('*');
        const classes = new Set();
        for (const el of all) {
            for (const c of el.classList) classes.add(c);
        }
        return [...classes].sort();
    }""")

    # Filter relevant class names
    keywords = ['restaurant', 'vendor', 'store', 'card', 'food', 'item', 'list', 'name', 'title', 'rating', 'star', 'promo', 'discount', 'offer', 'badge', 'tag', 'merchant']
    relevant = [c for c in all_classes if any(kw in c.lower() for kw in keywords)]
    print(f"\n[{platform}] Relevant CSS classes found ({len(relevant)}):")
    for c in relevant[:60]:
        print(f"  .{c}")

    # Try to get first restaurant card HTML
    card_candidates = [
        'div[class*="restaurant-item"]',
        'div[class*="restaurantItem"]',
        'div[class*="food-card"]',
        'div[class*="store-card"]',
        'div[class*="vendor-card"]',
        'div[class*="restaurant-card"]',
        'div[class*="restaurantCard"]',
        'div[class*="vendorCard"]',
        'div[class*="merchant-card"]',
        'div[class*="merchantCard"]',
        '[data-testid*="restaurant"]',
        '[data-testid*="vendor"]',
        '[data-testid*="store"]',
    ]

    print(f"\n[{platform}] Scanning for card selectors...")
    for sel in card_candidates:
        els = page.query_selector_all(sel)
        visible = [e for e in els if e.is_visible()]
        if visible:
            print(f"  FOUND {len(visible)} × '{sel}'")
            # Show first card structure
            try:
                html = visible[0].inner_html()
                print(f"    First card HTML (truncated):\n    {html[:800]}\n")
            except Exception as ex:
                print(f"    Could not get innerHTML: {ex}")
        else:
            if els:
                print(f"  {len(els)} (hidden) × '{sel}'")

    browser.close()


def main():
    with sync_playwright() as pw:
        inspect_page(pw, SHOPEEFOOD_URL, "ShopeeFood")
        inspect_page(pw, GRABFOOD_URL, "GrabFood")


if __name__ == "__main__":
    main()
