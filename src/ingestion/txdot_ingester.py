"""Texas TxDOT CRIS — ArcGIS FeatureServer ingester.

Ingests from the public FeatureServer endpoint:
  https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/
    TXDOT_Statewide_Bicyclist_Involved_Crashes/FeatureServer/0

NOTE: Despite the layer name ("Bicyclist Involved Crashes"), this endpoint
publishes the full statewide CRIS crash table (~3.09M rows). Only ~14,535
have bicyclist_involved_fl=1. The service description confirms this:
``txdot_ph_2.automated_sw.cris_crash``. See DECISIONS.md for the compliance
implications of using a mislabeled-but-public dataset.

Key design decisions:
  1. OID-range cursor: ``WHERE OBJECTID > {last_oid} ORDER BY OBJECTID ASC``
     avoids the skip/repeat problem with ``resultOffset`` on a moving table.
     The server's maxRecordCount is 2,000.
  2. Raw JSON pages preserved byte-for-byte in data/raw/bronze/txdot/.
  3. Tracks amend_supp_fl for downstream SCD2 handling of amended reports.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from src.ingestion.watermark import Watermark

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

FEATURE_SERVER_URL = (
    "https://services.arcgis.com/KTcxiTD9dsQw4r7Z/arcgis/rest/services/"
    "TXDOT_Statewide_Bicyclist_Involved_Crashes/FeatureServer/0/query"
)

PAGE_SIZE = 2000  # maxRecordCount for this layer
RAW_DIR = Path("data/raw/bronze/txdot")
MAX_RETRIES = 5
BACKOFF_BASE = 3.0  # ArcGIS servers can be slow; longer backoff

# Fields to request — requesting all (*) can cause timeouts on wide tables.
# We fetch all fields but in pages to avoid server-side timeout.
OUT_FIELDS = "*"


# ── Public API ───────────────────────────────────────────────────────────


def ingest(full_refresh: bool = False) -> int:
    """Ingest TxDOT CRIS data using OID-range cursor pagination.

    The OID cursor avoids the fundamental problem with ``resultOffset``:
    on a table that receives concurrent writes, offset-based paging silently
    skips records when new rows are inserted before the current offset, and
    repeats records when rows are deleted. An OID-based cursor is stable
    because OBJECTIDs are monotonically assigned and never reused.

    Args:
        full_refresh: If True, ignore watermark and start from OBJECTID 0.

    Returns:
        Total number of features fetched in this run.
    """
    wm = Watermark("txdot_cris")

    # Resume from last OID or start from 0
    last_oid: int = 0
    if not full_refresh and wm.is_fresh():
        last_oid = wm.get("last_max_oid", default=0)
        logger.info("Resuming TxDOT ingestion from OBJECTID > %d", last_oid)

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    total_features = 0
    page_num = wm.get("last_page_num", default=0) if not full_refresh else 0
    current_oid = last_oid

    with httpx.Client(timeout=120.0) as client:
        while True:
            # OID-range cursor: stable under concurrent writes
            where = f"OBJECTID > {current_oid}"

            params: dict[str, Any] = {
                "where": where,
                "outFields": OUT_FIELDS,
                "orderByFields": "OBJECTID ASC",
                "resultRecordCount": PAGE_SIZE,
                "f": "json",
                "returnGeometry": "true",
            }

            response = _fetch_with_retry(client, FEATURE_SERVER_URL, params)
            raw_bytes = response.content

            # Preserve raw response byte-for-byte
            raw_path = RAW_DIR / f"page_{page_num:06d}.json"
            raw_path.write_bytes(raw_bytes)

            data = response.json()

            # Check for ArcGIS error responses
            if "error" in data:
                error = data["error"]
                logger.error(
                    "ArcGIS error (code=%s): %s",
                    error.get("code"),
                    error.get("message"),
                )
                raise RuntimeError(f"ArcGIS query error: {error.get('message')}")

            features = data.get("features", [])
            if not features:
                logger.info(
                    "No more features from TxDOT at OBJECTID > %d",
                    current_oid,
                )
                break

            page_count = len(features)
            total_features += page_count

            # Advance OID cursor to the max OBJECTID in this page
            max_oid_in_page = max(f["attributes"]["OBJECTID"] for f in features)
            current_oid = max_oid_in_page

            logger.info(
                "TxDOT page %d: %d features (OID range %d→%d, total=%d)",
                page_num,
                page_count,
                current_oid - page_count + 1,
                current_oid,
                total_features,
            )

            page_num += 1

            # Save watermark every page for crash-safe resumption
            # (3M rows / 2k per page = ~1,545 pages — we want to survive restarts)
            if page_num % 50 == 0:
                wm.set("last_max_oid", current_oid)
                wm.set("last_page_num", page_num)
                wm.set("total_features", total_features)
                wm.save()
                logger.info(
                    "Checkpoint: saved watermark at OID %d, page %d",
                    current_oid,
                    page_num,
                )

            # If we got fewer than PAGE_SIZE, we've reached the end
            if page_count < PAGE_SIZE:
                break

    # Final watermark update
    wm.set("last_max_oid", current_oid)
    wm.set("last_page_num", page_num)
    wm.set("total_features", total_features)
    wm.set("content_hash", Watermark.content_hash(raw_bytes))
    wm.save()

    logger.info(
        "TxDOT ingestion complete: %d features across %d pages",
        total_features,
        page_num,
    )
    return total_features


# ── Internal helpers ─────────────────────────────────────────────────────


def _fetch_with_retry(
    client: httpx.Client,
    url: str,
    params: dict[str, Any],
) -> httpx.Response:
    """Fetch with exponential backoff for ArcGIS server errors and timeouts.

    ArcGIS FeatureServer can return:
    - HTTP 200 with an error JSON body (query timeout, invalid SQL)
    - HTTP 5xx under load
    - Network timeouts on wide-table queries
    """
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url, params=params)

            if resp.status_code >= 500:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(
                    "ArcGIS server error %d, retrying in %.1fs (attempt %d/%d)",
                    resp.status_code,
                    wait,
                    attempt + 1,
                    MAX_RETRIES,
                )
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp

        except httpx.TimeoutException:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Timeout on ArcGIS query, retrying in %.1fs (attempt %d/%d)",
                wait,
                attempt + 1,
                MAX_RETRIES,
            )
            time.sleep(wait)

        except httpx.TransportError as exc:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Transport error: %s, retrying in %.1fs (attempt %d/%d)",
                exc,
                wait,
                attempt + 1,
                MAX_RETRIES,
            )
            time.sleep(wait)

    raise RuntimeError(f"Failed to fetch TxDOT data after {MAX_RETRIES} attempts")
