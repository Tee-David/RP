# core/scraper_engine.py
import os
import time
import contextlib
from typing import List, Tuple, Optional, Dict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

__all__ = [
    "render_and_collect_pages",
    "generic_extract_listings_from_html",
    "generic_deep_crawl",
]

# -------- Runtime knobs via env --------
HEADLESS = os.getenv("RP_HEADLESS", "1") != "0"
NO_IMAGES = os.getenv("RP_NO_IMAGES", "0") == "1"
SCROLL_STEPS = int(os.getenv("RP_SCROLL_STEPS", "12") or "12")
PAGE_CAP = int(os.getenv("RP_PAGE_CAP", "30") or "30")
DEBUG = os.getenv("RP_DEBUG", "0") == "1"

# Common “list/grid ready” selectors we’ll wait for
DEFAULT_LIST_SELECTORS = [
    "[data-testid*='listing']",
    ".property-list, .property-listing, .listing, .listings, .property-grid, .grid",
    "section:has(article), .results, .search-results, .searchResult, .cards",
    "article[property], article[itemtype*='Offer'], article, li:has(a[href*='property'])",
]

# “Next / pagination” selectors we’ll click if present
DEFAULT_NEXT_SELECTORS = [
    "a[rel='next']",
    "button[aria-label*='Next' i], a[aria-label*='Next' i]",
    "a.page-next, a.next, .pagination-next a, .pager-next a",
    "li.next a, li.pagination-next a, .paginate_button.next",
]

# Accept cookies buttons (many sites)
COOKIE_SELECTORS = [
    "button#onetrust-accept-btn-handler",
    "button[aria-label*='accept' i]",
    "button:has-text('Accept')",
    "button:has-text('I agree')",
    "button:has-text('Allow all')",
    "button:has-text('Accept all')",
    "button:has-text('Got it')",
]

# ---------------- Playwright bootstrap ----------------
def _playwright_launch_kwargs() -> Dict:
    # import inside the function to avoid hard dependency at import time
    args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
    ]
    return {"headless": HEADLESS, "args": args}

def _block_images(page):
    if not NO_IMAGES:
        return
    def _route(route, request):
        rt = request.resource_type
        if rt in ("image", "media", "font"):
            return route.abort()
        return route.continue_()
    page.route("**/*", _route)

def _accept_cookies(page):
    for sel in COOKIE_SELECTORS:
        with contextlib.suppress(Exception):
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=1500)
                page.wait_for_timeout(350)

def _human_scroll(page, steps: int = SCROLL_STEPS, per_step_ms: int = 400):
    for _ in range(max(1, steps)):
        with contextlib.suppress(Exception):
            page.mouse.wheel(0, 1200)
        page.wait_for_timeout(per_step_ms)

def _wait_list_ready(page, selectors: List[str], timeout_ms: int = 12000) -> bool:
    for sel in selectors:
        with contextlib.suppress(Exception):
            page.wait_for_selector(sel, timeout=timeout_ms, state="visible")
            return True
    return False

def _click_next_if_present(page, selectors: List[str]) -> bool:
    """Try clicking any 'next' control. Returns True if navigation happened."""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_enabled():
                with page.expect_navigation(wait_until="load", timeout=15000):
                    loc.first.click()
                page.wait_for_load_state("domcontentloaded")
                return True
        except Exception:
            continue
    return False

def _discover_numeric_pages(page) -> List[str]:
    """Find numbered pagination links on the page; return absolute URLs."""
    try:
        anchors = page.locator("a[href]")
        urls = []
        count = min(anchors.count(), 2000)
        base = page.url
        for i in range(count):
            a = anchors.nth(i)
            href = a.get_attribute("href") or ""
            if not href:
                continue
            txt = (a.inner_text() or "").strip()
            if any(c.isdigit() for c in txt) and ("page" in href or "/p/" in href or "/pg/" in href or "/page/" in href):
                urls.append(urljoin(base, href))
        # uniq, preserve order
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                out.append(u)
                seen.add(u)
        return out[:PAGE_CAP]
    except Exception:
        return []

def _url_param_fallbacks(url: str, start_from: int = 2, cap: int = PAGE_CAP) -> List[str]:
    """
    Build candidate paginated URLs (?page=N, &page=N, /page/N).
    We'll generate a conservative list; sites that don't support them will just 404 or redirect.
    """
    out = []
    joiner = "&" if "?" in url else "?"
    for n in range(start_from, start_from + cap - 1):
        out.append(f"{url}{joiner}page={n}")
    base = url.rstrip("/")
    for n in range(start_from, start_from + cap - 1):
        out.append(f"{base}/page/{n}")
    # uniq, preserve order
    seen = set()
    uniq = []
    for u in out:
        if u not in seen:
            uniq.append(u)
            seen.add(u)
    return uniq[: cap - 1]

# ---------------- Public helpers ----------------
def render_and_collect_pages(
    start_url: str,
    list_ready_selectors: Optional[List[str]] = None,
    next_selectors: Optional[List[str]] = None,
    page_cap: Optional[int] = None,
    scroll_steps: Optional[int] = None,
) -> List[Tuple[str, str]]:
    """
    Drives Playwright to:
      - open start_url
      - accept cookies
      - scroll to trigger lazy-load
      - click "Next" buttons if present
      - OR follow numbered page links
      - OR fall back to ?page=/ /page/ URL patterns
    Returns list of (url, html) for each visited page (page 1..N).
    """
    from playwright.sync_api import sync_playwright
    max_pages = int(page_cap or PAGE_CAP)
    steps = int(scroll_steps or SCROLL_STEPS)
    list_sels = list_ready_selectors or DEFAULT_LIST_SELECTORS
    next_sels = next_selectors or DEFAULT_NEXT_SELECTORS

    results: List[Tuple[str, str]] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**_playwright_launch_kwargs())
        context = browser.new_context(viewport={"width": 1500, "height": 900})
        page = context.new_page()
        _block_images(page)

        def _collect():
            html = page.content()
            results.append((page.url, html))

        # PAGE 1
        page.goto(start_url, wait_until="domcontentloaded", timeout=45000)
        _accept_cookies(page)
        _wait_list_ready(page, list_sels, timeout_ms=15000)
        _human_scroll(page, steps=steps)
        _collect()

        # Strategy A: click "Next"
        pages_visited = 1
        while pages_visited < max_pages:
            clicked = _click_next_if_present(page, next_sels)
            if not clicked:
                break
            _wait_list_ready(page, list_sels, timeout_ms=10000)
            _human_scroll(page, steps=steps)
            _collect()
            pages_visited += 1

        # Strategy B: numeric page links (if we only saw 1 page from A)
        if pages_visited == 1:
            numeric = _discover_numeric_pages(page)
            for num_url in numeric[: max_pages - pages_visited]:
                try:
                    page.goto(num_url, wait_until="domcontentloaded", timeout=40000)
                    _wait_list_ready(page, list_sels, timeout_ms=10000)
                    _human_scroll(page, steps=steps)
                    _collect()
                    pages_visited += 1
                except Exception:
                    continue

        # Strategy C: URL param fallback if still only 1 page
        if pages_visited == 1:
            candidates = _url_param_fallbacks(start_url, start_from=2, cap=max_pages)
            for num_url in candidates[: max_pages - pages_visited]:
                try:
                    page.goto(num_url, wait_until="domcontentloaded", timeout=35000)
                    _wait_list_ready(page, list_sels, timeout_ms=8000)
                    _human_scroll(page, steps=steps)
                    _collect()
                    pages_visited += 1
                except Exception:
                    continue

        context.close()
        browser.close()

    return results


def generic_extract_listings_from_html(page_url: str, html: str) -> List[Dict]:
    """
    Very lightweight heuristic extractor to get *something* out:
    title, listing_url, price-ish text, location-ish text.
    Parsers can do better; this is a safety net.
    """
    soup = BeautifulSoup(html, "lxml")
    items: List[Dict] = []

    # Common card containers
    candidates = soup.select(
        "article, li, div.card, div[class*='listing'], div[class*='property'], .result, .search-result"
    )
    for node in candidates[:1000]:
        a = node.select_one("a[href]")
        if not a:
            continue
        href = a.get("href", "")
        if not href:
            continue
        url = urljoin(page_url, href)

        title_text = a.get_text(" ", strip=True) or node.get_text(" ", strip=True)
        title = (title_text[:160]).strip() if title_text else None

        text = node.get_text(" ", strip=True)
        # naive price/location heuristics
        price = None
        for tag in ["₦", "NGN", "N "]:
            if tag in text:
                idx = text.find(tag)
                price = text[idx : idx + 30]
                break

        location = None
        for key in ["Lagos", "Lekki", "Ikoyi", "Victoria Island", "Ajah", "Ikeja", "Yaba", "Surulere"]:
            if key.lower() in (text or "").lower():
                location = key
                break

        items.append(
            {
                "title": title or None,
                "listing_url": url,
                "price": price,
                "location": location,
                "description": text[:1000] if text else None,
                "source": page_url.split("/")[2] if "://" in page_url else page_url,
                "scrape_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def generic_deep_crawl(start_url: str, page_cap: Optional[int] = None) -> List[Dict]:
    """
    Full fallback path:
      - Render and paginate across many pages
      - Heuristically extract listing candidates
    """
    pages = render_and_collect_pages(start_url, page_cap=page_cap or PAGE_CAP)
    all_items: List[Dict] = []
    for url, html in pages:
        all_items.extend(generic_extract_listings_from_html(url, html))
    return all_items
