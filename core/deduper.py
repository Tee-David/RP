import hashlib

def compute_hash(title, price, location):
    raw = f"{title or ''}|{price or ''}|{location or ''}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def dedupe_listings(listings):
    seen = set()
    unique = []
    for l in listings:
        h = l.get('hash')
        if not h:
            continue
        if h in seen:
            continue
        seen.add(h)
        unique.append(l)
    return unique
