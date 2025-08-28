# core/geo.py
"""
Lightweight geocoding with OpenStreetMap Nominatim.

Features
- 1 req/sec rate limit (per Nominatim usage policy spirit)
- Persistent cache at logs/geocache.json
- Per-run cap via RP_MAX_GEOCODES (default 120)
- Can disable geocoding via RP_GEOCODE=0 (returns unchanged listings)
- Robust: skips blanks, handles timeouts, never throws

Env (cmd.exe examples)
  set RP_GEOCODE=1              # enable (default 1)
  set RP_MAX_GEOCODES=120       # per-run cap
  set RP_NET_RETRY_SECS=180     # already used elsewhere; honored here too
  set RP_DEBUG=1                # print debug

Input/Output
- Each listing dict may contain: 'location', 'estate_name', 'listing_url'
- We set listing['coordinates'] = {'lat': float, 'lng': float} on success
"""

import os, json, time, threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import requests

RP_DEBUG = os.getenv("RP_DEBUG") == "1"
RP_GEOCODE = os.getenv("RP_GEOCODE", "1") != "0"
RP_MAX_GEOCODES = int(os.getenv("RP_MAX_GEOCODES", "120"))
RP_NET_RETRY_SECS = int(os.getenv("RP_NET_RETRY_SECS", "180"))

# Where we persist geocode cache
CACHE_PATH = Path("logs") / "geocache.json"
CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)

# Nominatim requires a descriptive User-Agent incl. contact
UA = os.getenv(
    "NOMINATIM_UA",
    "RealtorsPractice/1.0 (+contact: you@example.com)"
)

_lock = threading.Lock()
_last_call_ts = 0.0


def _load_cache() -> Dict[str, Dict[str, float]]:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: Dict[str, Dict[str, float]]):
    try:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _rate_limit():
    global _last_call_ts
    with _lock:
        now = time.time()
        delta = now - _last_call_ts
        if delta < 1.05:  # ~1 req/sec
            time.sleep(1.05 - delta)
        _last_call_ts = time.time()


def _request_with_retry(session: requests.Session, url: str, params: dict, timeout: int = 30) -> Optional[requests.Response]:
    start = time.time()
    attempt = 0
    while True:
        attempt += 1
        try:
            _rate_limit()
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                return r
        except Exception:
            pass
        if time.time() - start > RP_NET_RETRY_SECS:
            return None
        time.sleep(min(6, 1 + attempt * 0.75))


def _clean_addr(s: str) -> str:
    s = (s or "").strip()
    # Cheap normalization to reduce cache misses
    return " ".join(s.split())


def _compose_query(listing: Dict[str, Any]) -> Optional[str]:
    loc = _clean_addr(str(listing.get("location") or ""))
    estate = _clean_addr(str(listing.get("estate_name") or ""))
    # Prefer the more specific text if present
    if estate and "estate" in estate.lower():
        q = f"{estate}, Lagos, Nigeria"
    elif loc:
        q = f"{loc}, Lagos, Nigeria" if "lagos" not in loc.lower() else loc
    else:
        # fallback to title if it looks location-ish
        title = _clean_addr(str(listing.get("title") or ""))
        if title:
            q = f"{title}, Lagos, Nigeria"
        else:
            return None
    return _clean_addr(q)


def geocode_address(session: requests.Session, query: str) -> Optional[Dict[str, float]]:
    """Geocode a single free-text address via Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "addressdetails": 0,
    }
    resp = _request_with_retry(session, url, params)
    if not resp:
        return None
    try:
        data = resp.json()
        if isinstance(data, list) and data:
            lat = float(data[0]["lat"])
            lon = float(data[0]["lon"])
            return {"lat": lat, "lng": lon}
    except Exception:
        return None
    return None


def geocode_listings(listings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Batch geocode. Mutates copies of the listings to add 'coordinates'.
    Returns a new list (does not modify original list in-place).
    """
    if not RP_GEOCODE or not listings:
        if RP_DEBUG:
            print("    [geo] geocoding disabled or no listings")
        return listings

    cache = _load_cache()
    out: List[Dict[str, Any]] = []
    used = 0

    with requests.Session() as s:
        s.headers.update({
            "User-Agent": UA,
            "Accept": "application/json,text/*,*/*;q=0.8",
        })

        for item in listings:
            # Clone to avoid side-effects upstream
            rec = dict(item)
            if rec.get("coordinates"):
                out.append(rec)
                continue

            q = _compose_query(rec)
            if not q:
                out.append(rec)
                continue

            # Cache hit?
            cached = cache.get(q)
            if cached and "lat" in cached and "lng" in cached:
                rec["coordinates"] = {"lat": cached["lat"], "lng": cached["lng"]}
                out.append(rec)
                continue

            # Respect per-run cap
            if used >= RP_MAX_GEOCODES:
                if RP_DEBUG:
                    print(f"    [geo] cap reached ({RP_MAX_GEOCODES}); skipping the rest")
                out.append(rec)
                continue

            coords = geocode_address(s, q)
            if coords:
                rec["coordinates"] = coords
                cache[q] = coords
                used += 1
            # even if miss, we keep the record; just without coordinates
            out.append(rec)

    # persist cache at end
    _save_cache(cache)

    if RP_DEBUG:
        print(f"    [geo] completed: used={used}, cache_size={len(cache)}")
    return out
