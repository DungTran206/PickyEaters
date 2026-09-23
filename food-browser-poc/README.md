# Food Platform Browser PoC 🍜

A minimal proof-of-concept that verifies whether an AI agent can open and interact with **ShopeeFood** and **GrabFood** websites, search for restaurants in a Vietnamese district, and extract publicly visible restaurant/food information.

> **This is a technical feasibility test — not the full Personal Food Agent.**

---

## Project Structure

```
food-browser-poc/
├── main.py          # CLI entry point
├── agent.py         # Minimal agent layer (rule-based, no LLM)
├── browser.py       # Playwright browser wrapper / tool functions
├── extractors.py    # Platform-specific data extraction
├── requirements.txt # Python dependencies
│
├── artifacts/
│   ├── screenshots/ # PNG screenshots taken during the run
│   ├── results/     # JSON output (shopeefood.json, grabfood.json)
│   └── feasibility_report.md
│
└── README.md
```

---

## Setup

```bash
# 1. Create and activate a virtual environment (optional but recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/macOS

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Install Playwright browser binaries (Chromium)
playwright install chromium
```

---

## Running

```bash
# Test both platforms (default — opens a visible browser window)
python main.py

# Test only ShopeeFood
python main.py --platform shopeefood

# Test only GrabFood
python main.py --platform grabfood

# Different district
python main.py --district "Hoàn Kiếm" --city "Hà Nội"

# Run headless (no visible browser window)
python main.py --headless

# Custom food request
python main.py --request "Tìm đồ ăn cay ở Cầu Giấy"
```

---

## Output

| Artifact | Description |
|---|---|
| `artifacts/screenshots/shopeefood_home.png` | ShopeeFood homepage |
| `artifacts/screenshots/shopeefood_search.png` | After search/navigation |
| `artifacts/screenshots/grabfood_home.png` | GrabFood homepage |
| `artifacts/screenshots/grabfood_search.png` | After location + scroll |
| `artifacts/results/shopeefood.json` | Extracted restaurant data |
| `artifacts/results/grabfood.json` | Extracted restaurant data |
| `artifacts/feasibility_report.md` | Full feasibility analysis |

---

## Example JSON Output

```json
{
  "platform": "ShopeeFood",
  "feasibility": {
    "website_accessible": true,
    "browser_interaction": true,
    "search_possible": true,
    "restaurant_cards_readable": true,
    "restaurant_detail_readable": false,
    "menu_readable": false,
    "promotion_readable": true,
    "blocked_by": null
  },
  "restaurants": [
    {
      "platform": "ShopeeFood",
      "restaurant_name": "Cơm Tấm Phúc Lộc Thọ",
      "address": null,
      "rating": 4.7,
      "category": null,
      "dish_name": null,
      "dish_price": null,
      "promotion": "Giảm 20%",
      "restaurant_url": "https://shopeefood.vn/ha-noi/..."
    }
  ]
}
```

---

## Safety Constraints

This PoC only interacts with publicly accessible, user-facing pages.

It does **NOT**:
- Bypass CAPTCHA or anti-bot mechanisms
- Reverse-engineer private APIs
- Use stored sessions or stolen cookies
- Attempt to defeat access controls

If the website blocks automation, the agent stops and reports `ACCESS_BLOCKED`.

---

## What Would Be Required for the Full Food Agent

1. **Selector maintenance** — Both platforms update their DOM regularly; need a selector registry or LLM-based element identification
2. **Anti-bot handling** — May need residential proxies or browser fingerprint randomisation
3. **Location precision** — Platforms need a specific address, not just a district name
4. **Login walls** — Some features require authenticated sessions
5. **Rate limiting** — Spacing requests to avoid IP bans
6. **LLM integration** — For natural-language query parsing and flexible data extraction
