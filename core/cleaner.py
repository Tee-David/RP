# core/cleaner.py
#
# Functions to normalize raw listing dictionaries into a consistent
# schema for downstream processing.  The normalizer ensures that each
# record contains the same keys and attempts to infer missing data such
# as bedrooms and bathrooms.  Currency values are converted to integers
# representing Nigerian Naira where possible.

import re
from typing import Any, Dict, Optional


# Define the canonical set of keys expected in a normalized listing.  If
# a key is missing from the input data the normalizer will provide a
# default of ``None`` or an empty list as appropriate.
ALL_KEYS = [
    "title",
    "price",
    "location",
    "property_type",
    "estate_name",
    "details",
    "land_size",
    "title_tag",
    "description",
    "promo_tags",
    "service_charge",
    "launch_timeline",
    "agent_name",
    "contact_info",
    "images",
    "listing_url",
    "coordinates",
    "price_per_sqm",
    "price_per_bedroom",
    "bedrooms",
    "bathrooms",
]

# Regular expressions for extracting numeric values from descriptive
# fields.  Many listings include the number of bedrooms and bathrooms
# only in the title or description, e.g. "3 Bed 2 Bath".
_BED_RE = re.compile(r"\b(\d+)\s*(?:bed|bd|bdr?)\b", re.I)
_BATH_RE = re.compile(r"\b(\d+)\s*(?:bath|ba|bth)\b", re.I)
_SQM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:sqm|square metres?)", re.I)


def _extract_int(pattern: re.Pattern, text: str) -> Optional[int]:
    match = pattern.search(text)
    return int(match.group(1)) if match else None


def _safe_float(num: Any) -> Optional[float]:
    try:
        return float(num)
    except (TypeError, ValueError):
        return None


def normalize_listing(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return a new dictionary with normalized fields.

    ``raw`` should be a dictionary as returned by one of the parser
    modules.  This function will extract or compute standard fields and
    ensure that all ``ALL_KEYS`` are present in the result.  Unknown
    keys from the raw dict are ignored.
    """
    result: Dict[str, Any] = {k: None for k in ALL_KEYS}

    # Copy simple fields directly if present.
    for key in [
        "title",
        "price",
        "location",
        "property_type",
        "estate_name",
        "details",
        "land_size",
        "title_tag",
        "description",
        "promo_tags",
        "service_charge",
        "launch_timeline",
        "agent_name",
        "contact_info",
        "listing_url",
    ]:
        if raw.get(key) is not None:
            result[key] = raw[key]

    # Ensure images is always a list
    imgs = raw.get("images")
    if isinstance(imgs, list):
        result["images"] = imgs
    elif imgs:
        result["images"] = [imgs]
    else:
        result["images"] = []

    # Use provided bedrooms/bathrooms if present; otherwise try to
    # extract from the title or description.
    for key, pattern in [("bedrooms", _BED_RE), ("bathrooms", _BATH_RE)]:
        val = raw.get(key)
        if isinstance(val, int):
            result[key] = val
        else:
            text = f"{raw.get('title', '')} {raw.get('description', '')}"
            result[key] = _extract_int(pattern, text)

    # Compute price per square metre and per bedroom if possible
    price = _safe_float(raw.get("price"))
    land_size = _safe_float(raw.get("land_size"))
    bedrooms = result.get("bedrooms")
    if price and land_size:
        result["price_per_sqm"] = price / land_size
    if price and bedrooms:
        result["price_per_bedroom"] = price / bedrooms

    # Coordinates may already be provided by the parser; copy through
    if raw.get("coordinates"):
        result["coordinates"] = raw["coordinates"]

    return result