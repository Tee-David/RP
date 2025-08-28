# parsers/specials.py
#
# Generic, config‑driven parser.  This module defines a mapping of
# site keys to per‑site hints (CSS selectors for listing cards, titles,
# prices, locations, images, etc.).  The ``scrape`` function uses
# these hints along with BeautifulSoup to extract raw listing
# dictionaries.  For brevity only a minimal implementation is
# provided here.  Extend this module to support additional sites and
# more sophisticated parsing logic.

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Any, Dict, List

from core.scraper_engine import fetch_adaptive


# RP_DEBUG environment flag to turn on debug logging if desired
import os
RP_DEBUG = os.getenv("RP_DEBUG") == "1"


# Per‑site configuration.  To add support for a new site simply
# include a new entry here with appropriate CSS selectors.  See
# README for guidance on choosing selectors.  The keys should match
# those in config.yaml.
CONFIGS: Dict[str, Dict[str, Any]] = {
    "npc": {
        "name": "Nigeria Property Centre",
        "url": "https://nigeriapropertycentre.com/",
        "list_paths": ["/for-sale", "/for-rent"],
        "lagos_paths": ["/property-for-sale/in/lagos", "/property-for-rent/in/lagos"],
        "card": "li.property-list, .property-list, .property, article",
        "title": "h2, .prop-title, a[title]",
        "price": ".price, .prop-price, .price-text",
        "location": ".location, .prop-location",
        "image": "img",
        "next_selectors": ["a[rel='next']", "li.next a", "a[aria-label*='Next']"],
        "page_param": "page",
        "search_param": None,
    },
    "propertypro": {
        "name": "PropertyPro Nigeria",
        "url": "https://propertypro.ng/",
        "list_paths": ["/property-for-sale", "/property-for-rent"],
        "lagos_paths": ["/property-for-sale/lagos", "/property-for-rent/lagos"],
        "card": "div.single-room-text, article.property, li.property",
        "title": "a h2, .single-room-text h2, h2 > a, .title a",
        "price": "span.propery-price, .price, .listings-price",
        "location": ".location, .listings-location, .single-room-location",
        "image": "img",
        "next_selectors": ["a[rel='next']", "li.next a", ".pagination a[aria-label*='Next']"],
        "page_param": "page",
        "search_param": "q",
    },
    "property24": {
        "name": "Property24 Nigeria",
        "url": "https://www.property24.com.ng/",
        "list_paths": ["/property-for-sale", "/property-to-rent"],
        "lagos_paths": ["/property-for-sale/lagos/all-homes", "/property-to-rent/lagos/all-homes"],
        "card": "div.p24_propertyTile, .p24_regularTile, article",
        "title": ".p24_regularTile .p24_title, .p24_title, h2 a",
        "price": ".p24_price, .p24_price strong",
        "location": ".p24_location, .p24_locationText, .p24_address",
        "image": "img",
        "next_selectors": ["a[rel='next']", "a[aria-label*='Next']", ".pagination a.next"],
        "page_param": "page",
        "search_param": "q",
    },
}


def _select_first(el: BeautifulSoup, selector_csv: str) -> Any:
    for css in selector_csv.split(","):
        node = el.select_one(css.strip())
        if node:
            return node
    return None


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node else ""


def scrape(base_url: str, site_key: str, max_pages: int = 1, query: str = None) -> List[Dict[str, Any]]:
    """Scrape listings for a site using the CONFIGS hints.

    ``base_url`` is the root URL to crawl (from config.yaml), ``site_key``
    identifies which CONFIGS entry to use.  ``max_pages`` limits the
    number of pages crawled; ``query`` may be used by some sites to
    restrict results (e.g. to Lagos).  Returns a list of raw listing
    dictionaries with keys such as title, price, location and images.
    """
    config = CONFIGS.get(site_key)
    if not config:
        return []
    listings: List[Dict[str, Any]] = []
    url = base_url
    for page in range(max_pages):
        html = fetch_adaptive(url)
        soup = BeautifulSoup(html, "html.parser")
        for card in soup.select(config["card"]):
            title_node = _select_first(card, config["title"])
            price_node = _select_first(card, config["price"])
            loc_node = _select_first(card, config["location"])
            img_node = _select_first(card, config["image"])
            listings.append({
                "title": _text(title_node),
                "price": _text(price_node),
                "location": _text(loc_node),
                "images": [img_node.get("src")] if img_node else [],
                "listing_url": title_node.get("href") if title_node and title_node.has_attr("href") else None,
            })
        # Find next page if available
        next_url = None
        for sel in config.get("next_selectors", []):
            link = soup.select_one(sel)
            if link and link.get("href"):
                next_url = urljoin(url, link["href"])
                break
        if not next_url:
            break
        url = next_url
    return listings