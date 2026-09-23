import sys
import json
sys.path.insert(0, ".")
from browser import BrowserSession

def main():
    b = BrowserSession(headless=True)
    b.start()

    url = "https://food.grab.com/vn/en/restaurant/burger-factory-base-2-delivery/5-C3CEAELZREMUGT"
    b.open_page(url, wait_until="networkidle", timeout=30000)
    b.wait(2000)

    res = b.page.evaluate("""() => {
        const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]')).map(s => {
            try { return JSON.parse(s.innerText); } catch(e) { return s.innerText; }
        });

        // Search for address in text or elements
        const elementsWithAddress = Array.from(document.querySelectorAll('*'))
            .filter(el => {
                const txt = el.innerText || '';
                return el.children.length === 0 && (txt.includes('Hà Nội') || txt.includes('District') || txt.includes('Quận') || txt.includes('Phường'));
            })
            .map(el => ({ tag: el.tagName, class: el.className, text: el.innerText }));

        return {
            scripts: scripts,
            addressElements: elementsWithAddress.slice(0, 5)
        };
    }""")
    print("GrabFood Address:")
    print(json.dumps(res, indent=2, ensure_ascii=False))
    b.close()

if __name__ == "__main__":
    main()
