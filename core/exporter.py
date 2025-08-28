# core/exporter.py
#
# Export cleaned listings to CSV and Excel files.  Each scraping run
# writes output into the ``exports/<site>`` directory with timestamped
# filenames.  The exporter ensures that all columns are present and
# serializes complex fields like image lists into strings.

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import Iterable, Dict, List

import openpyxl


CORE_COLUMNS = [
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


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _serialize(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return str(value)


def export_listings(site: str, listings: Iterable[Dict[str, Any]], out_dir: str = "exports") -> None:
    """Export a sequence of normalized listings to CSV and XLSX.

    ``site`` is used to create a subdirectory under ``out_dir``.  Files
    are named with the current timestamp to avoid collisions.
    """
    site_dir = Path(out_dir) / site
    site_dir.mkdir(parents=True, exist_ok=True)
    ts = _timestamp()
    csv_path = site_dir / f"{ts}_{site}.csv"
    xlsx_path = site_dir / f"{ts}_{site}.xlsx"

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CORE_COLUMNS)
        writer.writeheader()
        for item in listings:
            row = {col: _serialize(item.get(col)) for col in CORE_COLUMNS}
            writer.writerow(row)

    # Write Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(CORE_COLUMNS)
    for item in listings:
        row = [_serialize(item.get(col)) for col in CORE_COLUMNS]
        ws.append(row)
    wb.save(xlsx_path)