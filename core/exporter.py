# core/exporter.py
"""
Exporter for Realtors Practice.

- Saves listings to CSV and XLSX under exports/<site>/
- Skips export if there are 0 listings
- Filenames: YYYY-MM-DD_HH-MM-SS_<sitename>.csv|.xlsx
- Core columns enforced; extra fields are ignored (but won't break export)
"""

import os
import csv
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import openpyxl

RP_DEBUG = os.getenv("RP_DEBUG") == "1"

# Keep these aligned with cleaner.normalize_listing() output
CORE_COLUMNS = [
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
    "images",            # will serialize as comma-separated URLs
    "listing_url",
    "source",
    "scrape_timestamp",
    "coordinates",       # will serialize as "lat,lng"
    "hash"
]

def _ensure_folder(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

def _serialize_cell(value):
    """Make complex fields csv/xlsx-friendly."""
    if isinstance(value, dict) and "lat" in value and "lng" in value:
        return f"{value.get('lat')},{value.get('lng')}"
    if isinstance(value, (list, tuple)):
        # images list, amenities, etc.
        return ", ".join([str(v) for v in value if v is not None])
    return value if value is not None else ""

def export_listings(site: str, listings: List[Dict[str, Any]]) -> None:
    """
    Export listings for a single site into CSV and XLSX.
    Skips writing if listings is empty.
    """
    if not listings:
        if RP_DEBUG:
            print(f"    [export] {site}: skipped export (0 listings)")
        return

    out_dir = Path("exports") / site
    _ensure_folder(out_dir)

    stamp = _timestamp()
    base = out_dir / f"{stamp}_{site}"

    # --- CSV ---
    csv_path = str(base) + ".csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CORE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in listings:
            safe_row = {col: _serialize_cell(row.get(col)) for col in CORE_COLUMNS}
            writer.writerow(safe_row)

    # --- XLSX ---
    xlsx_path = str(base) + ".xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(CORE_COLUMNS)
    for row in listings:
        ws.append([_serialize_cell(row.get(col)) for col in CORE_COLUMNS])
    wb.save(xlsx_path)

    if RP_DEBUG:
        print(f"    [export] {site}: exported {len(listings)} → {csv_path}, {xlsx_path}")
