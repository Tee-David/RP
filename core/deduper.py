# core/deduper.py
#
# Helpers to remove duplicate listings.  Deduplication is performed
# using a hash of key fields to identify identical or near‑identical
# records.  This module can be extended to use more sophisticated
# fuzzy matching if required.

from hashlib import md5
from typing import Iterable, Dict, List


def compute_hash(item: Dict[str, str]) -> str:
    """Compute a unique hash for a listing based on its title, price
    and location.  Additional fields can be added to the key if
    necessary.  This is used to detect duplicates between scraping runs.
    """
    key = f"{item.get('title')}-{item.get('price')}-{item.get('location')}"
    return md5(key.encode("utf-8")).hexdigest()


def dedupe_listings(items: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    """Return a list with duplicates removed.  Items with identical
    computed hashes are considered duplicates and only the first
    encountered instance is kept."""
    seen = set()
    unique: List[Dict[str, str]] = []
    for item in items:
        h = compute_hash(item)
        if h not in seen:
            seen.add(h)
            unique.append(item)
    return unique