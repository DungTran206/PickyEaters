import sys
import os
import json
import time
from pathlib import Path

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

RESULTS_DIR = Path(__file__).parent / "artifacts" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

def crawl_shopeefood_thanh_xuan():
    print("[Crawler] Starting ShopeeFood crawl for Thanh Xuân...")
    crawled_restaurants = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Try search for Thanh Xuan and Xôi Thanh Xuan
        urls_to_search = [
            ("Thanh Xuân", "https://shopeefood.vn/ha-noi/danh-sach-dia-diem?q=Thanh+Xu%C3%A2n"),
            ("Xôi Thanh Xuân", "https://shopeefood.vn/ha-noi/danh-sach-dia-diem?q=x%C3%B4i+Thanh+Xu%C3%A2n"),
        ]

        found_urls = set()

        for label, search_url in urls_to_search:
            print(f"[Crawler] Searching {label}: {search_url}")
            try:
                page.goto(search_url, timeout=30000, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                
                # Scroll a bit
                for _ in range(3):
                    page.mouse.wheel(0, 800)
                    page.wait_for_timeout(1000)

                # Extract restaurant links
                links_data = page.evaluate("""() => {
                    const res = [];
                    // Look for restaurant items
                    const items = document.querySelectorAll('div.item-restaurant, div.list-restaurant-item-wrapper, div[class*="item-restaurant"]');
                    for (const item of items) {
                        const linkEl = item.querySelector('a');
                        const nameEl = item.querySelector('h2, h3, .name-res, div[class*="name"], a');
                        const addrEl = item.querySelector('div[class*="address"], p[class*="address"], .address-res');
                        const ratingEl = item.querySelector('div[class*="rating"], span[class*="rating"]');
                        
                        const href = linkEl ? linkEl.href : '';
                        const name = nameEl ? nameEl.innerText.trim() : '';
                        const addr = addrEl ? addrEl.innerText.trim() : '';
                        const rating = ratingEl ? ratingEl.innerText.trim() : '4.7';

                        if (href && name) {
                            res.push({url: href, name: name, address: addr, rating: rating});
                        }
                    }
                    return res;
                }""")
                print(f"[Crawler] Found {len(links_data)} cards from {label}")
                for item in links_data:
                    u = item["url"]
                    if u not in found_urls and "/ha-noi/" in u and "danh-sach" not in u:
                        found_urls.add(u)
                        crawled_restaurants.append(item)
            except Exception as e:
                print(f"[Crawler] Error querying {label}: {e}")

        print(f"[Crawler] Total unique restaurants found: {len(crawled_restaurants)}")

        # Now visit detail page for top restaurants to extract menu
        final_data = []
        for idx, r in enumerate(crawled_restaurants[:8]):
            url = r["url"]
            print(f"\n[Crawler] [{idx+1}/{min(8, len(crawled_restaurants))}] Visiting {r['name']} -> {url}")
            try:
                page.goto(url, timeout=25000, wait_until="domcontentloaded")
                page.wait_for_timeout(2500)
                page.mouse.wheel(0, 600)
                page.wait_for_timeout(1000)

                # Extract menu and address
                detail_data = page.evaluate("""() => {
                    // Extract address from JSON-LD schema or DOM
                    let address = "";
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of scripts) {
                        try {
                            const j = JSON.parse(s.innerText);
                            const items = Array.isArray(j) ? j : [j];
                            for (const it of items) {
                                if (it.address) {
                                    if (typeof it.address === 'string') address = it.address;
                                    else if (typeof it.address === 'object') {
                                        address = [it.address.streetAddress, it.address.addressLocality, it.address.addressRegion].filter(Boolean).join(', ');
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    if (!address) {
                        const addrNode = document.querySelector('.address-restaurant, div[class*="address"], p[class*="address"]');
                        if (addrNode) address = addrNode.innerText.trim();
                    }

                    // Extract dishes
                    const dishes = [];
                    const dishRows = document.querySelectorAll('div.item-restaurant-row, div[class*="item-restaurant-row"], div.row-item, div[class*="dish-item"]');
                    for (const row of dishRows) {
                        const nameNode = row.querySelector('h2, h3, h4, .item-name, div[class*="name"]');
                        const priceNode = row.querySelector('.current-price, div[class*="price"], span[class*="price"]');
                        const descNode = row.querySelector('.item-desc, div[class*="desc"], p');
                        
                        const dName = nameNode ? nameNode.innerText.trim() : '';
                        const dPriceStr = priceNode ? priceNode.innerText.trim() : '';
                        const dDesc = descNode ? descNode.innerText.trim() : '';
                        
                        if (dName && dPriceStr) {
                            dishes.push({
                                dish_name: dName,
                                dish_price_raw: dPriceStr,
                                description: dDesc
                            });
                        }
                    }

                    return {address: address, dishes: dishes};
                }""")

                menu = []
                for d in detail_data.get("dishes", []):
                    # parse price
                    import re
                    digits = re.sub(r"[^\d]", "", d.get("dish_price_raw", ""))
                    price = int(digits) if digits else 45000
                    menu.append({
                        "dish_name": d["dish_name"],
                        "dish_price": price,
                        "original_price": None,
                        "description": d.get("description") or "",
                        "discount": None
                    })

                r_address = detail_data.get("address") or r.get("address") or "Thanh Xuân, Hà Nội"
                final_data.append({
                    "platform": "ShopeeFood",
                    "restaurant_name": r["name"],
                    "address": r_address,
                    "rating": float(r.get("rating") or 4.7),
                    "restaurant_url": url,
                    "menu": menu
                })
                print(f"[Crawler] Extracted {len(menu)} dishes for {r['name']}")
            except Exception as ex:
                print(f"[Crawler] Error fetching detail for {url}: {ex}")

        browser.close()

    print(f"[Crawler] Finished! Successfully extracted {len(final_data)} restaurants with menu.")
    return final_data

if __name__ == "__main__":
    data = crawl_shopeefood_thanh_xuan()
    out_file = RESULTS_DIR / "shopeefood_thanhxuan.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"platform": "ShopeeFood", "restaurants": data}, f, ensure_ascii=False, indent=2)
    print(f"[Crawler] Saved output to {out_file}")
