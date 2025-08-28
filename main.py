#!/usr/bin/env python3
# main.py
#
# Entry point for the Realtor scraper.  This script loads configuration
# from ``config.yaml``, iterates over enabled sites, fetches raw
# listings using site parsers, normalizes the listings, optionally
# geocodes them and exports the results to CSV and XLSX files.

import logging
import os
from pathlib import Path
from typing import List, Dict, Any

import yaml

from core import cleaner, deduper, geo, exporter, dispatcher


def load_config(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_site(site_key: str, site_info: Dict[str, Any]) -> None:
    logger = logging.getLogger(site_key)
    url = site_info["url"]
    parser_type = site_info.get("parser", "special")
    parser_adapter = dispatcher.get_parser(site_key)
    try:
        # For the specials parser we pass the site_key so it can look
        # up per‑site selectors.  Other parsers may accept only the
        # base URL argument.
        raw_listings: List[Dict[str, Any]] = parser_adapter.scrape(
            url, site_key=site_key
        )
    except Exception as exc:
        logger.error(f"Error scraping {site_key}: {exc}")
        return
    if not raw_listings:
        logger.info(f"No listings returned for {site_key}")
        return
    # Normalize and deduplicate
    normalized = [cleaner.normalize_listing(item) for item in raw_listings]
    unique = deduper.dedupe_listings(normalized)
    # Geocode addresses (can be disabled via env var)
    if not (os.getenv("RP_GEOCODE_DISABLED") == "1"):
        geo.geocode_listings(unique)
    exporter.export_listings(site_key, unique)
    logger.info(f"Exported {len(unique)} listings for {site_key}")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    config_path = Path(__file__).parent / "config.yaml"
    config = load_config(config_path)
    enabled = config.get("enabled_sites", [])
    sites = config.get("sites", {})
    for key in enabled:
        info = sites.get(key)
        if not info:
            logging.warning(f"Site {key} is enabled but not defined in config")
            continue
        run_site(key, info)


if __name__ == "__main__":
    main()