# core/geo.py
#
# Lightweight geocoding utilities built on top of the OpenStreetMap
# Nominatim API.  This module caches results to avoid unnecessary
# repeated lookups and rate limits requests to be respectful of the
# service.  See the README for details on configuring cache paths and
# geocoding limits.

import json
import os
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import requests


GEOCACHE_PATH = Path("logs/geocache.json")
GEOCODE_DELAY_SECONDS = 1  # minimum delay between requests
MAX_GEOCODES_PER_RUN = int(os.getenv("RP_MAX_GEOCODES", "100"))


def _load_cache() -> Dict[str, Tuple[float, float]]:
    if GEOCACHE_PATH.exists():
        with GEOCACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: Dict[str, Tuple[float, float]]) -> None:
    GEOCACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GEOCACHE_PATH.open("w", encoding="utf-8") as f:
        json.dump(cache, f)


def _geocode(address: str) -> Optional[Tuple[float, float]]:
    """Call Nominatim to geocode an address.  Returns (lat, lon) or
    None if not found."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1,
    }
    time.sleep(GEOCODE_DELAY_SECONDS)
    try:
        res = requests.get(url, params=params, headers={"User-Agent": "RealtorScraper"}, timeout=30)
        res.raise_for_status()
    except requests.RequestException:
        return None
    data = res.json()
    if not data:
        return None
    lat = data[0].get("lat")
    lon = data[0].get("lon")
    return (float(lat), float(lon)) if lat and lon else None


def geocode_listings(listings: Iterable[Dict[str, Any]]) -> None:
    """Augment listings in place with latitude/longitude coordinates.

    Uses a simple cache to avoid repeated requests for the same address
    and respects the ``MAX_GEOCODES_PER_RUN`` limit to avoid hitting
    rate limits.  Updates the ``coordinates`` field of each listing if
    geocoding succeeds.
    """
    cache = _load_cache()
    geocoded = 0
    for item in listings:
        if item.get("coordinates") or not item.get("location"):
            continue
        loc = item["location"]
        if loc in cache:
            item["coordinates"] = cache[loc]
            continue
        if geocoded >= MAX_GEOCODES_PER_RUN:
            break
        coords = _geocode(loc)
        if coords:
            cache[loc] = coords
            item["coordinates"] = coords
            geocoded += 1
    if geocoded > 0:
        _save_cache(cache)