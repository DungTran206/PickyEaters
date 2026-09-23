import sys
import json
sys.path.insert(0, ".")
from browser import BrowserSession

def main():
    b = BrowserSession(headless=True)
    b.start()
    url = "https://shopeefood.vn/ha-noi/com-ngon-sai-gon-com-ga-com-suon-ngon"
    print("Navigating to ShopeeFood restaurant:", url)
    b.open_page(url, wait_until="networkidle", timeout=30000)
    b.wait(3000)
    b.take_screenshot("shopeefood_real_restaurant")

    menu_data = b.page.evaluate("""() => {
        const items = [];
        // Look for dish rows or items
        const rows = document.querySelectorAll(".item-restaurant-row, [class*='item-restaurant-row'], .row-item-restaurant, .item-restaurant");
        rows.forEach(r => {
            const name = r.querySelector(".item-restaurant-name, .item-restaurant-total, h2, h3, [class*='name']");
            const price = r.querySelector(".current-price, [class*='price']");
            const desc = r.querySelector(".item-restaurant-desc, [class*='desc']");
            if (name) {
                items.push({
                    name: name.innerText.trim(),
                    price: price ? price.innerText.trim() : null,
                    desc: desc ? desc.innerText.trim() : null
                });
            }
        });

        // Let's also collect all class names in this page
        const classes = new Set();
        document.querySelectorAll('*').forEach(el => {
            if (el.className && typeof el.className === 'string') {
                el.className.split(' ').forEach(c => {
                    const lc = c.toLowerCase();
                    if (lc.includes('dish') || lc.includes('item') || lc.includes('menu') || lc.includes('price')) {
                        classes.add(c);
                    }
                });
            }
        });

        return {
            title: document.title,
            total_rows: rows.length,
            total_items: items.length,
            classes: Array.from(classes).slice(0, 30),
            sample: items.slice(0, 10),
            body_snippet: document.body.innerText.slice(0, 1000)
        };
    }""")
    print("ShopeeFood Restaurant Result:")
    print(json.dumps(menu_data, indent=2, ensure_ascii=False))
    b.close()

if __name__ == "__main__":
    main()
