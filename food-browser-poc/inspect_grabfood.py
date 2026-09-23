"""
inspect_grabfood.py — Targeted GrabFood DOM inspector.
Goes to /vn/en/ home (which shows restaurants already) and dumps card HTML.
"""
from __future__ import annotations
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=80)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="vi-VN",
        )
        page = ctx.new_page()
        
        # GrabFood home already shows restaurants
        print("[*] Loading GrabFood home...")
        page.goto("https://food.grab.com/vn/en/", wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(4_000)
        
        # Scroll down to trigger lazy load
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(2_000)
        
        page.screenshot(path="artifacts/screenshots/grab_inspect.png")
        
        # Find all divs that have class names containing restaurant/card/merchant
        data = page.evaluate("""() => {
            const candidates = [];
            const all = document.querySelectorAll('div, a, li');
            for (const el of all) {
                const cls = el.className || '';
                if (typeof cls !== 'string') continue;
                if (cls.match(/restaurant|merchant|card|vendor|store/i)) {
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 100 && rect.height > 50 && rect.top > 0) {
                        candidates.push({
                            tag: el.tagName,
                            classes: cls.trim(),
                            text: el.innerText.slice(0, 200),
                            children: el.children.length,
                            href: el.href || '',
                        });
                    }
                }
            }
            return candidates.slice(0, 40);
        }""")
        
        print(f"\n[GrabFood] Found {len(data)} candidate elements:")
        for item in data:
            print(f"\n  <{item['tag']} class='{item['classes']}' children={item['children']} href={item['href'][:60]}>")
            print(f"  text: {item['text'][:150]}")
        
        # Also try specific selectors
        test_selectors = [
            "[class*='restaurantCard']",
            "[class*='merchantCard']",
            "[class*='restaurant-card']",
            "[class*='cardComponent']",
            "[class*='listComponent']",
            "[class*='storeDeeplink']",
            "a[class*='restaurant']",
            "a[href*='/vn/en/restaurant/']",
        ]
        
        print("\n\n[GrabFood] Testing selectors:")
        for sel in test_selectors:
            els = page.query_selector_all(sel)
            visible = [e for e in els if e.is_visible()]
            if visible:
                print(f"\n  '{sel}' → {len(visible)} visible elements")
                try:
                    html = visible[0].inner_html()
                    print(f"  First innerHTML: {html[:400]}")
                    text = visible[0].inner_text()
                    print(f"  First text: {text[:200]}")
                except Exception as ex:
                    print(f"  Error: {ex}")
        
        browser.close()

if __name__ == "__main__":
    main()
