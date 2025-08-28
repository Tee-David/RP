# core/utils.py
import re
import logging
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict

# --------------------------
# Time & IDs
# --------------------------

def get_timestamp() -> str:
    """Standard timestamp used across the pipeline."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def make_hash(*parts: Any) -> str:
    """Stable SHA256 of important fields (None-safe)."""
    s = "||".join("" if p is None else str(p) for p in parts)
    return sha256(s.encode("utf-8", errors="ignore")).hexdigest()

# --------------------------
# Location filter helpers
# --------------------------

_LAGOS_PATTERNS = [
    r"\blagos\b",
    r"\blekki\b",
    r"\bikeja\b",
    r"\bajah\b",
    r"\bsangotedo\b",
    r"\bchevron\b",
    r"\bagungi\b",
    r"\bikate\b",
    r"\bvi\b",                # Victoria Island (short)
    r"\bvictoria\s+island\b",
    r"\boniru\b",
    r"\bikoyi\b",
    r"\byaba\b",
    r"\bsurulere\b",
    r"\bmaryland\b",
    r"\bilupeju\b",
    r"\bagbara\b",
    r"\boshodi\b",
    r"\bialimosho\b",
    r"\bepe\b",
    r"\bawoyaya\b",
    r"\babijo\b",
    r"\blakowe\b",
    r"\beleko\b",
    r"\blekki\s*phase\s*1\b",
]

def is_lagos_like(text: str) -> bool:
    """
    Return True if a string looks like it's about Lagos or the Lekki–Epe corridor.
    Used to filter out irrelevant listings.
    """
    if not text:
        return False
    t = text.lower()
    for pat in _LAGOS_PATTERNS:
        if re.search(pat, t):
            return True
    return False

# --------------------------
# Currency / numeric helpers
# --------------------------

_NAIRA_PAT = re.compile(r"(?:₦|\bngn\b|\bn\b)", re.I)
_NUM_PAT = re.compile(r"[\d,.]+")
_PER_SQM_PAT = re.compile(r"/\s*(?:sqm|m\^?2|m2)\b", re.I)

def parse_naira(value: str) -> int | None:
    """
    Normalize price-like strings into integer Naira.
    Examples:
      '₦ 25,000,000' -> 25000000
      'NGN 1.2m'     -> 1200000
      'N350k'        -> 350000
    Returns None if unrecognized.
    """
    if not value:
        return None
    s = str(value).strip().lower()

    # remove currency symbol/label
    s = _NAIRA_PAT.sub("", s)

    # detect multipliers
    mult = 1
    if "b" in s and not "bed" in s:   # guard against "2 bed"
        mult = 1_000_000_000
    elif "m" in s:
        mult = 1_000_000
    elif "k" in s:
        mult = 1_000

    # strip non-numeric except separators
    nums = _NUM_PAT.findall(s)
    if not nums:
        return None
    raw = "".join(nums)
    try:
        # handle decimals like "1.25" with multiplier
        if "." in raw:
            val = float(raw.replace(",", ""))
            return int(val * mult)
        # pure integer with separators
        return int(raw.replace(",", "")) * mult
    except Exception:
        return None

def is_price_per_sqm(text: str) -> bool:
    return bool(_PER_SQM_PAT.search(text or ""))

# --------------------------
# Safe dict helpers
# --------------------------

def safe_get(d: Dict[str, Any], *keys, default=None):
    """
    Safely fetch nested keys from a dict.
    Example:
        safe_get(item, "price", "amount", default=0)
    """
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur

# --------------------------
# Logging helpers
# --------------------------

def log_site_error(site_key: str, msg: str, exc: Exception = None):
    """Uniform logging for site errors."""
    if exc:
        logging.exception(f"[{site_key}] {msg}: {exc}")
    else:
        logging.error(f"[{site_key}] {msg}")
