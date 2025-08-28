# core/utils.py
#
# Miscellaneous utility functions used throughout the scraper.  These
# include helpers for generating timestamps, hashing, matching Lagos
# locations, parsing Nigerian Naira prices and other convenience
# functions.

import re
import time
from hashlib import md5
from typing import Any, Iterable, Optional


def get_timestamp() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def make_hash(values: Iterable[str]) -> str:
    """Return an MD5 hash of a sequence of strings."""
    h = md5()
    for val in values:
        if val:
            h.update(val.encode("utf-8"))
    return h.hexdigest()


# Patterns for matching Lagos addresses.  These can be tuned or
# replaced entirely by a list of locations in config.yaml.
_LAGOS_PATTERNS = [
    re.compile(r"\blagos\b", re.I),
    re.compile(r"\blekki\b", re.I),
    re.compile(r"\bajah\b", re.I),
    re.compile(r"\bsangotedo\b", re.I),
    re.compile(r"\bikate\b", re.I),
]


def is_lagos_like(location: str) -> bool:
    """Return True if the location appears to be within the Lagos
    metropolitan area.  Uses simple regex matching; override with a
    config‑driven approach as needed."""
    if not location:
        return False
    for pattern in _LAGOS_PATTERNS:
        if pattern.search(location):
            return True
    return False


_NAIRA_RE = re.compile(r"₦?\s*(\d+(?:[.,]\d+)*)(?:\s*(?:million|m))?", re.I)


def parse_naira(value: Any) -> Optional[int]:
    """Convert a currency string to an integer representing Naira.

    Accepts values like ``₦3.5M`` or ``25000000`` and returns an integer
    amount.  Returns None if the value cannot be parsed.
    """
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    match = _NAIRA_RE.search(value.replace(",", ""))
    if not match:
        return None
    num = match.group(1)
    amount = float(num)
    # Check for millions shorthand
    if re.search(r"m(?:illion)?", value, re.I):
        amount *= 1_000_000
    return int(amount)


def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """Safely get a key from a dict or return default."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default