"""Montgomery County, MD — Socrata / SODA API ingester.

Ingests three crash-reporting datasets from data.montgomerycountymd.gov:
  - bhju-22kf  Crash Reporting – Incidents Data   (~124,770 rows)
  - mmzv-x632  Crash Reporting – Drivers Data      (~219,644 rows)
  - n7fk-dce5  Crash Reporting – Non-Motorists Data (~7,498 rows)

Key design decisions:
  1. Deterministic pagination: ``$order=report_number`` prevents the silent
     skip-and-repeat problem that bare ``$offset`` causes under concurrent writes.
  2. Incremental watermark: uses the ``crash_date_time`` field to fetch only
     records newer than the last successful run, while also re-fetching the
     watermark day itself to catch late-arriving records.
  3. Raw preservation: every JSON response page is stored byte-for-byte in
     ``data/raw/bronze/moco/{dataset_id}/`` alongside a manifest.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from src.ingestion.watermark import Watermark

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

BASE_URL = "https://data.montgomerycountymd.gov/resource"
BULK_CSV_URL = "https://data.montgomerycountymd.gov/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD"

DATASETS = {
    "bhju-22kf": {
        "name": "Crash Reporting – Incidents Data",
        "order_field": "report_number",
        "date_field": "crash_date_time",
    },
    "mmzv-x632": {
        "name": "Crash Reporting – Drivers Data",
        "order_field": "report_number",
        "date_field": "crash_date_time",
    },
    "n7fk-dce5": {
        "name": "Crash Reporting – Non-Motorists Data",
        "order_field": "report_number",
        "date_field": "crash_date_time",
    },
}

PAGE_SIZE = 5000  # Socrata default max is 50k; 5k is safe under throttling
RAW_DIR = Path("data/raw/bronze/moco")
MAX_RETRIES = 5
BACKOFF_BASE = 2.0  # seconds — exponential backoff for throttling


# ── Public API ───────────────────────────────────────────────────────────


def ingest_all(
    app_token: str | None = None,
    full_refresh: bool = False,
) -> dict[str, int]:
    """Ingest all three MoCo datasets incrementally.

    Args:
        app_token: Optional Socrata app token to lift anonymous throttling.
        full_refresh: If True, ignore watermarks and re-fetch everything.

    Returns:
        Dict mapping dataset_id → total rows fetched in this run.
    """
    results = {}
    for dataset_id, meta in DATASETS.items():
        count = ingest_dataset(
            dataset_id=dataset_id,
            order_field=meta["order_field"],
            date_field=meta["date_field"],
            app_token=app_token,
            full_refresh=full_refresh,
        )
        results[dataset_id] = count
        logger.info(
            "Finished %s (%s): %d rows fetched",
            dataset_id,
            meta["name"],
            count,
        )
    return results


def ingest_dataset(
    dataset_id: str,
    order_field: str,
    date_field: str,
    app_token: str | None = None,
    full_refresh: bool = False,
) -> int:
    """Ingest a single Socrata dataset with incremental watermark.

    Pagination uses ``$order={order_field}`` for determinism. Incremental
    mode filters with ``$where={date_field} >= '{watermark}'`` and re-fetches
    the watermark day to catch late arrivals (deduplication is downstream).

    Raw JSON pages are preserved byte-for-byte in the bronze layer.
    """
    wm = Watermark(f"moco_{dataset_id}")

    # Build incremental filter
    where_clause = None
    if not full_refresh and wm.is_fresh():
        last_date = wm.get("last_max_date")
        if last_date:
            # Re-fetch from the watermark date to catch late arrivals
            where_clause = f"{date_field} >= '{last_date}'"
            logger.info(
                "Incremental fetch for %s: %s", dataset_id, where_clause
            )

    # Set up output directory for raw pages
    out_dir = RAW_DIR / dataset_id
    out_dir.mkdir(parents=True, exist_ok=True)

    token = app_token or os.getenv("SOCRATA_APP_TOKEN")
    headers = {}
    if token:
        headers["X-App-Token"] = token

    total_rows = 0
    offset = 0
    page_num = 0
    max_date_seen: str | None = wm.get("last_max_date")

    with httpx.Client(timeout=60.0, headers=headers) as client:
        while True:
            # Build SoQL query — deterministic order is critical
            params: dict[str, Any] = {
                "$order": order_field,
                "$limit": PAGE_SIZE,
                "$offset": offset,
            }
            if where_clause:
                params["$where"] = where_clause

            url = f"{BASE_URL}/{dataset_id}.json"
            response = _fetch_with_retry(client, url, params)

            # Preserve raw response byte-for-byte
            raw_bytes = response.content
            raw_path = out_dir / f"page_{page_num:06d}.json"
            raw_path.write_bytes(raw_bytes)

            records = response.json()
            if not records:
                logger.info(
                    "No more records for %s at offset %d", dataset_id, offset
                )
                break

            page_count = len(records)
            total_rows += page_count

            # Track the max date for the next incremental run
            for record in records:
                record_date = record.get(date_field)
                if record_date and (
                    max_date_seen is None or record_date > max_date_seen
                ):
                    max_date_seen = record_date

            logger.info(
                "%s page %d: %d rows (offset=%d, total=%d)",
                dataset_id,
                page_num,
                page_count,
                offset,
                total_rows,
            )

            offset += page_count
            page_num += 1

            # If we got fewer than PAGE_SIZE, we've reached the end
            if page_count < PAGE_SIZE:
                break

    # Update watermark
    wm.set("last_max_date", max_date_seen)
    wm.set("last_offset", offset)
    wm.set("last_row_count", total_rows)
    wm.set("last_page_count", page_num)
    wm.set("content_hash", Watermark.content_hash(raw_bytes))
    wm.save()

    return total_rows


# ── Internal helpers ─────────────────────────────────────────────────────


def _fetch_with_retry(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
) -> httpx.Response:
    """Fetch with exponential backoff for Socrata throttling (HTTP 429).

    Also retries on 5xx errors up to MAX_RETRIES times.
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, params=params)

            if resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Throttled (429) on %s, backing off %.1fs (attempt %d/%d)",
                    url,
                    wait,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "Server error %d on %s, retrying in %.1fs",
                    resp.status_code,
                    url,
                    wait,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp

        except httpx.TransportError as exc:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Transport error on %s: %s, retrying in %.1fs",
                url,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"Failed to fetch {url} after {MAX_RETRIES} attempts"
    )
