# main.py
import os
import sys
import time
import logging
from typing import Dict, Tuple

from core.dispatcher import get_parser
from core.cleaner import normalize_listing
from core.geo import geocode_listings
from core.exporter import export_listings
from core.utils import is_lagos_like

# ---------------- LOGGING (console + file) ----------------
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    filename="logs/scraper.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
console = logging.StreamHandler(sys.stdout)
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(console)

# ---------------- ENV / SETTINGS ----------------
# Retry wall-clock cap on network errors (seconds)
RP_NET_RETRY_SECS = int(os.getenv("RP_NET_RETRY_SECS", "180"))
# Whether to retry even when a scrape returns zero items
RP_RETRY_ON_ZERO = os.getenv("RP_RETRY_ON_ZERO", "0") == "1"
# Fallback chain to offer parsers (requests -> playwright -> scraperapi)
FALLBACK_ORDER = [s.strip() for s in os.getenv("RP_FALLBACK", "requests,playwright").split(",") if s.strip()]
# Optional global search hint some generic parsers can use
GLOBAL_SEARCH = os.getenv("RP_SEARCH", "").strip()
FILTERS = {"search_query": GLOBAL_SEARCH} if GLOBAL_SEARCH else {}

# ---------------- SITE URL DIRECTORY (50 sites) ----------------
SITES: Dict[str, str] = {
    "npc": "https://nigeriapropertycentre.com/",
    "propertypro": "https://propertypro.ng/",
    "privateproperty": "https://www.privateproperty.com.ng/",
    "property24": "https://www.property24.com.ng/",
    "hutbay": "https://www.hutbay.com/",
    "lamudi": "https://www.lamudi.com.ng/",
    "jiji": "https://jiji.ng/real-estate",
    "vconnect": "https://www.vconnect.com/",
    "nigerianpropertymarket": "https://nigerianpropertymarket.com/",
    "propertylisthub": "https://propertylisthub.com/",
    "quicktellerhomes": "https://homes.quickteller.com/",
    "naijahouses": "https://www.naijahouses.com/",
    "oparahrealty": "https://oparahrealty.com/",
    "lodges": "https://www.lodges.ng/",
    "olist": "https://www.olist.ng/real-estate",
    "realtorng": "https://www.realtor.ng/",
    "myproperty": "https://www.myproperty.ng",
    "houseafrica": "https://www.houseafrica.com.ng",
    "propertyguru": "https://propertyguru.com.ng/",
    "buyletlive": "https://buyletlive.com/",
    "cwlagos": "https://cwlagos.com/",
    "landng": "https://land.ng/",
    "lagosproperty": "https://lagosproperty.net/",
    "ramos": "https://ramosrealestateng.com/",
    "edenoasis": "https://www.edenoasisrealty.com/",
    "adronhomes": "https://adronhomesproperties.com/",
    "naijalandlord": "https://www.naijalandlord.com/",
    "trovit": "https://homes.trovit.ng/",
    "nazaprimehive": "https://hive.nazaprime.com.ng",
    "nigeriapropertyzone": "https://nigeriapropertyzone.com.ng/",
    "castles": "http://castles.com.ng/",
    "thinkmint": "http://buyrealestate.thinkmint.ng/",
    "realestatenigeria": "https://www.realestatenigeria.com",
    "tradebanq": "https://www.tradebanq.com",
    "landmall": "https://www.landmall.ng/",
    "giddaa": "https://giddaa.com/",
    "realtorintl": "https://www.realtor.com/international/ng/",
    "facibus": "https://facibushousing.com",
    "ownahome": "https://ownahome.ng/",
    "estateintel": "https://estateintel.com/",
    "spleet": "https://spleet.africa/",
    "rentsmallsmall": "https://rentsmallsmall.ng/",
    "cuddlerealty": "https://cuddlerealty.com/",
    "takooka_props": "https://properties.takooka.com/",
    "jaat_properties": "https://takooka.com/jaat-properties.php",
    "gtexthomes": "https://gtexthomes.com/",
    "ashproperties": "https://ashpropertiesng.com/",
    "propertieslinkng": "https://propertieslinkng.com/",
    "ubosieleh": "https://ubosieleh.com/",
    "brokerfield": "https://brokerfieldrealestate.com/",
}

ENABLED_SITES = list(SITES.keys())  # all 50

# ---------------- SCRAPE + RETRY WRAPPER ----------------
def try_scrape_with_retry(site_key: str, base_url: str) -> list:
    """
    Call parser.scrape() passing the kwargs many parsers expect:
        fallback_order, filters, site, site_key
    Use a simple backoff retry for network-y failures, for up to RP_NET_RETRY_SECS.
    Optionally retry on zero results if RP_RETRY_ON_ZERO=1.
    """
    parser = get_parser(site_key)
    start = time.time()
    attempt = 0

    while True:
        attempt += 1
        try:
            raw = parser.scrape(
                fallback_order=FALLBACK_ORDER,
                filters=FILTERS,
                site={"key": site_key, "url": base_url, "name": site_key},
                site_key=site_key,
            )
            if raw and len(raw) > 0:
                return raw
            if RP_RETRY_ON_ZERO:
                elapsed = time.time() - start
                if elapsed >= RP_NET_RETRY_SECS:
                    return raw or []
                sleep_s = min(6, 1 + attempt * 0.75)
                logging.info(f"{site_key}: 0 items, retrying in {sleep_s:.1f}s (elapsed {int(elapsed)}s/{RP_NET_RETRY_SECS}s)…")
                time.sleep(sleep_s)
                continue
            return raw or []
        except Exception as e:
            elapsed = time.time() - start
            if elapsed >= RP_NET_RETRY_SECS:
                logging.error(f"{site_key}: network/parser error; giving up after {int(elapsed)}s: {e}")
                return []
            sleep_s = min(10, 1 + attempt * 0.85)
            logging.info(f"{site_key}: error, retrying in {sleep_s:.1f}s (elapsed {int(elapsed)}s/{RP_NET_RETRY_SECS}s)…")
            time.sleep(sleep_s)

# ---------------- ONE SITE RUN ----------------
def run_site(site_key: str) -> Tuple[int, str]:
    base_url = SITES.get(site_key, "")
    if not base_url:
        logging.info(f"{site_key}: no base URL; skipping.")
        return 0, base_url

    logging.info(f"Scraping {site_key} -> {base_url}")

    # 1) Scrape (with retry wrapper)
    raw_items = try_scrape_with_retry(site_key, base_url)
    if not raw_items:
        logging.info(f"{site_key}: skipped export (0 listings).")
        return 0, base_url

    # 2) Normalize + Lagos filter
    cleaned = []
    for r in raw_items:
        try:
            n = normalize_listing(r, site=site_key)
        except Exception:
            continue
        if is_lagos_like(f"{n.get('location','')} {n.get('title','')}"):
            cleaned.append(n)

    if not cleaned:
        logging.info(f"{site_key}: skipped export (no Lagos listings).")
        return 0, base_url

    # 3) Geocode
    geocoded = geocode_listings(cleaned)

    # 4) Export (CSV/XLSX)
    try:
        export_listings(site_key, geocoded)
    except Exception as e:
        logging.error(f"{site_key}: export failed: {e}")
        return 0, base_url

    logging.info(f"Exported {len(geocoded)} listings for {site_key}")
    return len(geocoded), base_url

# ---------------- MAIN ----------------
def main():
    logging.info("Realtors Practice Scraper Entry\n")
    summary: Dict[str, Tuple[int, str]] = {}

    for site in ENABLED_SITES:
        try:
            count, url = run_site(site)
        except Exception as e:
            logging.error(f"{site}: FAILED with {e}")
            count, url = 0, SITES.get(site, "")
        summary[site] = (count, url)

    # Final report
    logging.info("\n=== SCRAPE REPORT ===")
    success_sites = 0
    total = 0
    for site, (count, url) in summary.items():
        if count > 0:
            logging.info(f"Found {count} listings from {site} ({url})")
            success_sites += 1
            total += count

    zero_sites = [s for s, (c, _) in summary.items() if c == 0]
    if success_sites == 0:
        logging.info("No listings found.")
    else:
        logging.info(f"Successful sites: {success_sites} / {len(summary)} | Total listings: {total}")
    if zero_sites:
        logging.info(f"Zero-listing sites: {', '.join(zero_sites)}")

if __name__ == "__main__":
    main()
