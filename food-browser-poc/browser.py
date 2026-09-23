"""
browser.py — Low-level Playwright wrapper.

Exposes simple tool-functions that the agent can call:
  open_page(), click(), type_text(), scroll(), extract_visible_content(),
  take_screenshot(), close()
"""

import re
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext, TimeoutError as PWTimeout

SCREENSHOT_DIR = Path(__file__).parent / "artifacts" / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

VIEWPORT = {"width": 1280, "height": 900}


class BrowserSession:
    """Manages one Playwright browser session."""

    def __init__(self, headless: bool = False, slow_mo: int = 150):
        self._pw = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.headless = headless
        self.slow_mo = slow_mo
        self._screenshot_index = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            slow_mo=self.slow_mo,
            args=["--start-maximized"],
        )
        self._context = self._browser.new_context(
            viewport=VIEWPORT,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="vi-VN",
        )
        self.page = self._context.new_page()
        print("[Browser] Session started (Chromium).")
        return self

    def close(self):
        if self._browser:
            self._browser.close()
        if self._pw:
            self._pw.stop()
        print("[Browser] Session closed.")

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def open_page(self, url: str, wait_until: str = "domcontentloaded", timeout: int = 30_000) -> str:
        print(f"[Browser] Navigating → {url}")
        try:
            self.page.goto(url, wait_until=wait_until, timeout=timeout)
            self.page.wait_for_timeout(2_000)
            actual = self.page.url
            print(f"[Browser] Page loaded: {actual}")
            return actual
        except PWTimeout:
            print(f"[Browser] TIMEOUT loading {url}")
            return self.page.url

    # ------------------------------------------------------------------
    # Popup / dialog handling
    # ------------------------------------------------------------------

    def dismiss_common_popups(self):
        """Try to close cookie banners, location modals, login prompts."""
        dismiss_selectors = [
            # Generic close / accept buttons (broad)
            "button:has-text('Đồng ý')",
            "button:has-text('Chấp nhận')",
            "button:has-text('OK')",
            "button:has-text('Đóng')",
            "button:has-text('Close')",
            "button:has-text('Accept')",
            "button:has-text('Got it')",
            # Cookie banners
            "[id*='cookie'] button",
            "[class*='cookie'] button",
            # Location / address dialogs — we want to keep them for interaction,
            # so we only close unknown popups.
            "[class*='modal-close']",
            "[class*='popup-close']",
            "[aria-label='Close']",
            "[aria-label='Đóng']",
        ]
        closed = []
        for sel in dismiss_selectors:
            try:
                btn = self.page.query_selector(sel)
                if btn and btn.is_visible():
                    btn.click()
                    time.sleep(0.5)
                    closed.append(sel)
            except Exception:
                pass
        if closed:
            print(f"[Browser] Dismissed popup(s): {closed}")

    # ------------------------------------------------------------------
    # Interaction helpers
    # ------------------------------------------------------------------

    def click(self, selector: str, timeout: int = 5_000) -> bool:
        try:
            self.page.click(selector, timeout=timeout)
            self.page.wait_for_timeout(500)
            print(f"[Browser] Clicked: {selector}")
            return True
        except Exception as exc:
            print(f"[Browser] Click failed ({selector}): {exc}")
            return False

    def click_text(self, text: str, timeout: int = 5_000) -> bool:
        """Click an element that contains the given text."""
        selector = f"text={text}"
        return self.click(selector, timeout=timeout)

    def type_text(self, selector: str, text: str, clear_first: bool = True) -> bool:
        try:
            el = self.page.wait_for_selector(selector, timeout=5_000)
            if clear_first:
                el.triple_click()
            el.type(text, delay=60)
            print(f"[Browser] Typed '{text}' into {selector}")
            return True
        except Exception as exc:
            print(f"[Browser] Type failed ({selector}): {exc}")
            return False

    def press_key(self, key: str):
        self.page.keyboard.press(key)

    def scroll(self, direction: str = "down", amount: int = 800):
        if direction == "down":
            self.page.mouse.wheel(0, amount)
        else:
            self.page.mouse.wheel(0, -amount)
        self.page.wait_for_timeout(800)
        print(f"[Browser] Scrolled {direction} {amount}px")

    def wait(self, ms: int = 2000):
        self.page.wait_for_timeout(ms)

    def wait_for_selector(self, selector: str, timeout: int = 10_000) -> bool:
        try:
            self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except PWTimeout:
            return False

    # ------------------------------------------------------------------
    # Content extraction
    # ------------------------------------------------------------------

    def get_title(self) -> str:
        return self.page.title()

    def get_url(self) -> str:
        return self.page.url

    def query_all_texts(self, selector: str) -> list[str]:
        """Return .inner_text() for every matching element."""
        try:
            elements = self.page.query_selector_all(selector)
            return [el.inner_text().strip() for el in elements if el.is_visible()]
        except Exception:
            return []

    def query_all_attrs(self, selector: str, attr: str) -> list[str]:
        try:
            elements = self.page.query_selector_all(selector)
            return [el.get_attribute(attr) or "" for el in elements]
        except Exception:
            return []

    def extract_visible_content(self, max_chars: int = 8000) -> str:
        """
        Grab all visible text from the page body.
        Useful for LLM-based parsing or quick inspection.
        """
        try:
            text = self.page.evaluate(
                """() => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode(node) {
                                const el = node.parentElement;
                                if (!el) return NodeFilter.FILTER_REJECT;
                                const style = window.getComputedStyle(el);
                                if (style.display === 'none' || style.visibility === 'hidden') {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    const parts = [];
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = node.textContent.trim();
                        if (t.length > 1) parts.push(t);
                    }
                    return parts.join(' ');
                }"""
            )
            return text[:max_chars]
        except Exception as exc:
            print(f"[Browser] extract_visible_content error: {exc}")
            return ""

    def query_elements(self, selector: str) -> list:
        """Return raw ElementHandle list."""
        try:
            return self.page.query_selector_all(selector)
        except Exception:
            return []

    def count_elements(self, selector: str) -> int:
        return len(self.query_elements(selector))

    def element_text(self, element) -> str:
        try:
            return element.inner_text().strip()
        except Exception:
            return ""

    def element_attr(self, element, attr: str) -> Optional[str]:
        try:
            return element.get_attribute(attr)
        except Exception:
            return None

    def is_visible(self, selector: str) -> bool:
        try:
            el = self.page.query_selector(selector)
            return el is not None and el.is_visible()
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Screenshots
    # ------------------------------------------------------------------

    def take_screenshot(self, name: str) -> Path:
        self._screenshot_index += 1
        safe_name = re.sub(r"[^\w\-]", "_", name)
        path = SCREENSHOT_DIR / f"{safe_name}.png"
        self.page.screenshot(path=str(path), full_page=False)
        print(f"[Browser] Screenshot saved: {path.name}")
        return path
