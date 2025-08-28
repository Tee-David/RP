# core/cleaner.py
"""
Normalize raw listing dicts into a consistent schema expected by exporter.

Input:  loosely-structured dict from parsers (may be missing many fields)
Output: normalized dict with all expected keys set (None/"" if missing)
"""

import re
from typing import Dict, Any
from core.utils import (
    parse_naira,
    is_price_per_sqm,
    get_timestamp,
    make_hash,
)

# Keep aligned with exporter.CORE_COLUMNS
ALL_KEYS = [
    "title",
    "price",
    "price_per_sqm",
    "price_per_bedroom",
    "location",
    "estate_name",
    "property_type",
    "bedrooms",
    "bathrooms",
    "toilets",
    "bq",
    "land_size",
    "title_tag",
    "description",
    "promo_tags",
    "initial_deposit",
    "payment_plan",
    "service_charge",
    "launch_timeline",
    "agent_name",
    "contact_info",
    "images",
    "listing_url",
    "source",
    "scrape_timestamp",
    "coordinates",
    "hash",
]

_INT_PAT = re.compile(r"\b(\d+)\b")
_BED_PAT = re.compile(r"(\d+)\s*(?:bed|br|bedroom)s?\b", re.I)
_BATH_PAT = re.compile(r"(\d+)\s*(?:bath|ba|bathroom)s?\b", re.I)
_TOILET_PAT = re.compile(r"(\d+)\s*(?:toilet)s?\b", re.I)
_BQ_PAT = re.compile(r"\bbq\b|\bb\.?q\.?\b|\bboy[’'`s\s-]*quarters?\b", re.I)
_SIZE_PAT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:sqm|m\^?2|m2|sq\.?m)", re.I)
_TITLE_DOC_PAT = re.compile(r"\b(C of O|C\.? of O|Governor'?s? Consent|Gov(?:ernor'?s?)? Consent|Excision|Deed of Assignment)\b", re.I)
_PROMO_PAT = re.compile(r"(?:deposit|initial\s*deposit|payment\s*plan|installment|instalment|months?\s*plan|\b\d+\s*months?\b|\b\d+\s*years?\b)", re.I)

def _first_nonempty(*vals):
    for v in vals:
        if v:
            return v
    return None

def _extract_size(text: str) -> str | None:
    m = _SIZE_PAT.search(text or "")
    return f"{m.group(1)} sqm" if m else None

def _extract_beds(text: str) -> int | None:
    m = _BED_PAT.search(text or "")
    return int(m.group(1)) if m else None

def _extract_baths(text: str) -> int | None:
    m = _BATH_PAT.search(text or "")
    return int(m.group(1)) if m else None

def _extract_toilets(text: str) -> int | None:
    m = _TOILET_PAT.search(text or "")
    return int(m.group(1)) if m else None

def _extract_title_tag(text: str) -> str | None:
    m = _TITLE_DOC_PAT.search(text or "")
    return m.group(1) if m else None

def _extract_promo(text: str) -> str | None:
    m = _PROMO_PAT.search(text or "")
    return m.group(0) if m else None

def _compute_price_per_sqm(price_naira: int | None, size_text: str | None) -> int | None:
    if not price_naira or not size_text:
        return None
    m = _INT_PAT.search(size_text)
    if not m:
        return None
    try:
        sqm = float(m.group(1))
        if sqm > 0:
            return int(price_naira / sqm)
    except Exception:
        return None
    return None

def _compute_price_per_bedroom(price_naira: int | None, beds: int | None) -> int | None:
    if not price_naira or not beds:
        return None
    try:
        if beds > 0:
            return int(price_naira / beds)
    except Exception:
        return None
    return None

def normalize_listing(src: Dict[str, Any], site: str | None = None) -> Dict[str, Any]:
    """
    Create a normalized listing dict from a raw parser item.
    """
    title = (src.get("title") or "").strip()
    desc  = (src.get("description") or "").strip()
    loc   = (src.get("location") or "").strip()
    ptxt  = (src.get("price") or "").strip()

    # price normalization
    price = parse_naira(ptxt)
    # explicit per-sqm if present like "₦100,000/sqm"
    price_per_sqm = None
    if is_price_per_sqm(ptxt):
        price_per_sqm = parse_naira(ptxt.split("/")[0])

    soup_text = " ".join([title, desc, loc, ptxt])
    bedrooms = _first_nonempty(src.get("bedrooms"), _extract_beds(soup_text))
    bathrooms = _first_nonempty(src.get("bathrooms"), _extract_baths(soup_text))
    toilets = _first_nonempty(src.get("toilets"), _extract_toilets(soup_text))
    bq = 1 if _BQ_PAT.search(soup_text) else (src.get("bq") or 0)
    land_size = _first_nonempty(src.get("land_size"), _extract_size(soup_text))
    title_tag = _first_nonempty(src.get("title_tag"), _extract_title_tag(soup_text))
    promo_tags = _first_nonempty(src.get("promo_tags"), _extract_promo(soup_text))

    price_per_sqm = price_per_sqm or _compute_price_per_sqm(price, land_size)
    price_per_bedroom = _compute_price_per_bedroom(price, bedrooms)

    imgs = src.get("images") or []
    if isinstance(imgs, str):
        imgs = [imgs]

    out = {
        "title": title or None,
        "price": price,
        "price_per_sqm": price_per_sqm,
        "price_per_bedroom": price_per_bedroom,
        "location": loc or None,
        "estate_name": src.get("estate_name"),
        "property_type": src.get("property_type"),
        "bedrooms": bedrooms,
        "bathrooms": bathrooms,
        "toilets": toilets,
        "bq": bq,
        "land_size": land_size,
        "title_tag": title_tag,
        "description": desc or None,
        "promo_tags": promo_tags,
        "initial_deposit": src.get("initial_deposit"),
        "payment_plan": src.get("payment_plan"),
        "service_charge": src.get("service_charge"),
        "launch_timeline": src.get("launch_timeline"),
        "agent_name": src.get("agent_name"),
        "contact_info": src.get("contact_info"),
        "images": imgs,
        "listing_url": src.get("listing_url"),
        "source": src.get("source") or site,
        "scrape_timestamp": get_timestamp(),
        "coordinates": src.get("coordinates"),
        "hash": make_hash(title, price, loc),
    }

    for k in ALL_KEYS:
        if k not in out:
            out[k] = None

    return out
