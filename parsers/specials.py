# parsers/specials.py
# Generic, config-driven parser with:
# - Lagos-scoped list paths when supported
# - Optional site search query support (adds ?q= or similar)
# - Pagination via explicit "Next" link or fallback ?page=N
# - Merges embedded JSON-LD + visible cards
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
import re, os, json
from core.scraper_engine import fetch_adaptive

RP_DEBUG = os.getenv("RP_DEBUG") == "1"

# Per-site hints. You can add more sites here anytime.
# search_param: optional query string param to pass a search term (e.g., "Lagos")
CONFIGS = {
    "npc": {
        "name":"Nigeria Property Centre","url":"https://nigeriapropertycentre.com/",
        "list_paths":["/for-sale","/for-rent"],
        "lagos_paths":["/property-for-sale/in/lagos","/property-for-rent/in/lagos"],
        "card":"li.property-list, .property-list, .property, article",
        "title":"h2, .prop-title, a[title]",
        "price":".price, .prop-price, .price-text",
        "location":".location, .prop-location",
        "image":"img",
        "next_selectors":["a[rel='next']","li.next a","a[aria-label*='Next']"],
        "page_param":"page",
        "search_param": None,
    },
    "propertypro": {
        "name":"PropertyPro Nigeria","url":"https://propertypro.ng/",
        "list_paths":["/property-for-sale","/property-for-rent"],
        "lagos_paths":["/property-for-sale/lagos","/property-for-rent/lagos"],
        "card":"div.single-room-text, article.property, li.property",
        "title":"a h2, .single-room-text h2, h2 > a, .title a",
        "price":"span.propery-price, .price, .listings-price",
        "location":".location, .listings-location, .single-room-location",
        "image":"img",
        "next_selectors":["a[rel='next']","li.next a",".pagination a[aria-label*='Next']"],
        "page_param":"page",
        "search_param": "q",
    },
    "property24": {
        "name":"Property24 Nigeria","url":"https://www.property24.com.ng/",
        "list_paths":["/property-for-sale","/property-to-rent"],
        "lagos_paths":["/property-for-sale/lagos/all-homes","/property-to-rent/lagos/all-homes"],
        "card":"div.p24_propertyTile, .p24_regularTile, article",
        "title":".p24_regularTile .p24_title, .p24_title, h2 a",
        "price":".p24_price, .p24_price strong",
        "location":".p24_location, .p24_locationText, .p24_address",
        "image":"img",
        "next_selectors":["a[rel='next']","a[aria-label*='Next']",".pagination a.next"],
        "page_param":"page",
        "search_param": "q",
    },
    "buyletlive": {
        "name":"BuyLetLive","url":"https://buyletlive.com/",
        "list_paths":["/properties"],
        "lagos_paths":["/properties?state=lagos"],
        "card":"div.property-card, div[class*=PropertyCard], article, li",
        "title":"h2 a, .property-card h2 a, [class*=PropertyCard] a[href*='/property/']",
        "price":".price, [class*=Price], .amount",
        "location":".location, [class*=Location], .address",
        "image":"img",
        "next_selectors":["a[rel='next']","button[aria-label*='Next']",".pagination a.next"],
        "page_param":"page",
        "search_param": "q",
    },
    # Fallback for any domain not listed explicitly
}

GENERIC_CARD = "div[class*=listing], div[class*=property], article, li"
GENERIC_TITLE = "h1, h2, h3, .title, a"
GENERIC_PRICE = ".price, .amount, [class*=price]"
GENERIC_LOCATION = ".location, .address, .region, .area, [class*=location]"
GENERIC_IMAGE = "img"

def _first(el, selector_csv):
    if not selector_csv:
        return None
    for css in [c.strip() for c in selector_csv.split(",")]:
        node = el.select_one(css)
        if node:
            return node
    return None

def _text(el):
    return el.get_text(" ", strip=True) if el else ""

def _next_page_by_link(soup, current_url, next_selectors):
    for sel in next_selectors or []:
        a = soup.select_one(sel)
        if a and a.get("href"):
            return urljoin(current_url, a["href"])
    return None

def _next_page_by_param(current_url, page_num, page_param):
    parts = list(urlsplit(current_url))
    qs = dict(parse_qsl(parts[3]))
    qs[page_param] = str(page_num)
    parts[3] = urlencode(qs)
    return urlunsplit(parts)

def _apply_search_param(url, search_param, query):
    if not (search_param and query):
        return url
    parts = list(urlsplit(url))
    qs = dict(parse_qsl(parts[3]))
    # Append search term; don’t overwrite if already present
    if search_param not in qs:
        qs[search_param] = query
    parts[3] = urlencode(qs)
    return urlunsplit(parts)

def _harvest_from_embedded_json(embedded_json_list):
    items = []
    def push(obj):
        addr = obj.get("address")
        if isinstance(addr, dict):
            loc = addr.get("addressLocality") or addr.get("streetAddress") or addr.get("addressRegion")
        else:
            loc = addr if isinstance(addr, str) else None
        imgs = obj.get("image")
        images = imgs if isinstance(imgs, list) else ([imgs] if imgs else [])
        items.append({
            "title": obj.get("name") or obj.get("title"),
            "price": obj.get("price") or obj.get("priceValue"),
            "location": loc,
            "property_type": obj.get("@type") or obj.get("propertyType"),
            "estate_name": None,
            "details": "",
            "land_size": None,
            "title_tag": None,
            "description": obj.get("description"),
            "promo_tags": None,
            "service_charge": None,
            "launch_timeline": None,
            "agent_name": (obj.get("seller") or {}).get("name") if isinstance(obj.get("seller"), dict) else None,
            "contact_info": None,
            "images": images,
            "listing_url": obj.get("url"),
            "coordinates": None,
            "source": None,
            "scrape_timestamp": None,
            "hash": None,
        })
    def walk(o):
        if isinstance(o, dict):
            if any(k in o for k in ("@type","name")) and any(k in o for k in ("price","address","url","image")):
                push(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    for blob in embedded_json_list:
        walk(blob)
    return items

def _scrape_list_page(url, cfg, fallback_order, site_key, page_idx):
    card_sel = (cfg.get("card") or GENERIC_CARD).strip()
    html, method, embedded = fetch_adaptive(url, card_sel.split(",")[0].strip(), fallback_order, site_key, page_idx)
    if RP_DEBUG:
        print(f"    fetched via: {method or 'none'} -> {url}")
    if not html:
        return None, []

    soup = BeautifulSoup(html, "lxml")

    # Embedded JSON
    items = []
    json_items = _harvest_from_embedded_json(embedded)
    if json_items:
        items.extend(json_items)

    # Visible cards
    cards = soup.select(card_sel) or soup.select(GENERIC_CARD)
    for box in cards:
        title = _text(_first(box, cfg.get("title", GENERIC_TITLE)))
        price = _text(_first(box, cfg.get("price", GENERIC_PRICE)))
        location = _text(_first(box, cfg.get("location", GENERIC_LOCATION)))
        img_el = _first(box, cfg.get("image", GENERIC_IMAGE))
        img = img_el.get("src") if img_el and img_el.get("src") else None
        a = _first(box, "a[href]")
        href = urljoin(url, a.get("href")) if a and a.get("href") else None
        if not (title or price or location or href):
            continue
        items.append({
            "title": title,
            "price": price,
            "location": location,
            "property_type": None,
            "estate_name": None,
            "details": "",
            "land_size": None,
            "title_tag": None,
            "description": None,
            "promo_tags": None,
            "service_charge": None,
            "launch_timeline": None,
            "agent_name": None,
            "contact_info": None,
            "images": [img] if img else [],
            "listing_url": href or url,
            "coordinates": None,
            "source": cfg.get("name"),
            "scrape_timestamp": None,
            "hash": None,
        })

    # Pagination: explicit next link/button
    next_url = _next_page_by_link(soup, url, cfg.get("next_selectors"))
    # Fallback: numeric ?page=N param
    if not next_url and cfg.get("page_param"):
        next_url = _next_page_by_param(url, page_idx + 1, cfg["page_param"])
    return next_url, items

def scrape(fallback_order, filters, start_url=None, site=None, site_key=None):
    key = site_key or (site.get("key") if site else None)
    # Merge config or generic
    cfg = CONFIGS.get(key) or {
        "name": site.get("name") if site else "Unknown",
        "url": site.get("url") if site else "",
        "list_paths": [""],
        "card": GENERIC_CARD,
        "title": GENERIC_TITLE,
        "price": GENERIC_PRICE,
        "location": GENERIC_LOCATION,
        "image": GENERIC_IMAGE,
        "next_selectors": ["a[rel='next']", "a[aria-label*='Next']", ".pagination a.next"],
        "page_param": "page",
        "search_param": None,
    }

    base = (cfg["url"] or (site.get("url") if site else "")).rstrip("/")
    # Prefer lagos_paths when present; else use list_paths
    list_paths = cfg.get("lagos_paths") or cfg.get("list_paths", [""])

    # Optional search query (e.g., "Lagos") – passed from main via config.yaml
    search_query = None
    if filters and isinstance(filters, dict):
        search_query = filters.get("search_query")

    all_items, seen = [], set()
    for path in list_paths:
        url = urljoin(base + "/", path.lstrip("/"))
        # Apply simple per-site search param if configured
        url = _apply_search_param(url, cfg.get("search_param"), search_query)

        pages = 0
        empty_streak = 0
        while url and pages < int(os.getenv("RP_PAGE_CAP", "40")):
            pages += 1
            next_url, items = _scrape_list_page(url, cfg, fallback_order, key or "site", pages)
            if RP_DEBUG:
                print(f"    page {pages}: +{len(items)} items")
            for it in items:
                u = (it.get("listing_url") or "") + "|" + (it.get("title") or "")
                if u and u not in seen:
                    it["source"] = it.get("source") or cfg.get("name")
                    all_items.append(it); seen.add(u)

            if not items:
                empty_streak += 1
            else:
                empty_streak = 0
            if empty_streak >= 2:  # stop after 2 consecutive empty pages
                break
            url = next_url
    return all_items
