"""NHTSA FARS — annual bulk ZIP file ingester.

Downloads national CSV ZIPs from:
  https://static.nhtsa.gov/nhtsa/downloads/FARS/{YEAR}/National/FARS{YEAR}NationalCSV.zip

Key design decisions:
  1. Restatement detection: FARS silently revises prior-year files in place
     (e.g. the 2023 file has a Last-Modified of 2026-04-01). We store
     Last-Modified + ETag + SHA-256 hash per year to detect when a re-download
     contains different data than the previous pull.
  2. Conditional fetch: uses If-Modified-Since / If-None-Match to avoid
     redundant downloads when the remote file hasn't changed.
  3. Raw ZIPs go to gitignored data/downloads/fars/; extracted CSVs go to
     data/raw/bronze/fars/{year}/.
"""

from __future__ import annotations

import hashlib
import logging
import zipfile
from pathlib import Path
from typing import Any

import httpx

from src.ingestion.watermark import Watermark

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────────

FARS_URL_TEMPLATE = (
    "https://static.nhtsa.gov/nhtsa/downloads/FARS/"
    "{year}/National/FARS{year}NationalCSV.zip"
)

# We focus on recent years relevant to a contact pipeline.
# FARS covers 1975–2024, but anything before ~2020 is too old for leads.
DEFAULT_YEARS = list(range(2020, 2025))

DOWNLOAD_DIR = Path("data/downloads/fars")
RAW_DIR = Path("data/raw/bronze/fars")
MAX_RETRIES = 3
BACKOFF_BASE = 5.0


# ── Public API ───────────────────────────────────────────────────────────


def ingest(
    years: list[int] | None = None,
    full_refresh: bool = False,
) -> dict[int, dict[str, Any]]:
    """Download and extract FARS bulk files for the specified years.

    Args:
        years: List of years to fetch. Defaults to 2020–2024.
        full_refresh: If True, re-download even if the remote file hasn't changed.

    Returns:
        Dict mapping year → {status, files, restated} where:
        - status: "downloaded" | "not_modified" | "error"
        - files: list of extracted CSV filenames
        - restated: True if the content changed since last download
    """
    if years is None:
        years = DEFAULT_YEARS

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for year in years:
        result = _ingest_year(year, full_refresh=full_refresh)
        results[year] = result
        logger.info("FARS %d: %s", year, result["status"])

    return results


# ── Per-year ingestion ───────────────────────────────────────────────────


def _ingest_year(
    year: int,
    full_refresh: bool = False,
) -> dict[str, Any]:
    """Download and extract FARS data for a single year.

    Uses conditional HTTP (If-Modified-Since / If-None-Match) to skip
    re-downloads when the remote file hasn't changed. Computes SHA-256 of
    the ZIP to detect silent restatements.
    """
    wm = Watermark(f"fars_{year}")
    url = FARS_URL_TEMPLATE.format(year=year)
    zip_path = DOWNLOAD_DIR / f"FARS{year}NationalCSV.zip"
    extract_dir = RAW_DIR / str(year)

    # Build conditional request headers
    headers: dict[str, str] = {}
    if not full_refresh and wm.is_fresh():
        last_modified = wm.get("last_modified")
        etag = wm.get("etag")
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        if etag:
            headers["If-None-Match"] = etag

    # Download
    try:
        response = _download_with_retry(url, headers)
    except RuntimeError as exc:
        logger.error("Failed to download FARS %d: %s", year, exc)
        return {"status": "error", "files": [], "restated": False}

    if response.status_code == 304:
        logger.info("FARS %d: not modified since last download", year)
        return {"status": "not_modified", "files": [], "restated": False}

    # Save ZIP
    zip_bytes = response.content
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(zip_bytes)

    # Compute hash for restatement detection
    current_hash = hashlib.sha256(zip_bytes).hexdigest()
    previous_hash = wm.get("content_hash")
    restated = previous_hash is not None and current_hash != previous_hash

    if restated:
        logger.warning(
            "FARS %d RESTATED: content hash changed from %.8s to %.8s",
            year,
            previous_hash,
            current_hash,
        )

    # Extract CSVs
    extract_dir.mkdir(parents=True, exist_ok=True)
    extracted_files = _extract_zip(zip_path, extract_dir)

    # Update watermark
    wm.set("content_hash", current_hash)
    wm.set("last_modified", response.headers.get("Last-Modified"))
    wm.set("etag", response.headers.get("ETag"))
    wm.set("zip_size_bytes", len(zip_bytes))
    wm.set("extracted_files", extracted_files)
    wm.set("restated", restated)
    wm.save()

    return {
        "status": "downloaded",
        "files": extracted_files,
        "restated": restated,
    }


# ── Internal helpers ─────────────────────────────────────────────────────


def _extract_zip(zip_path: Path, extract_dir: Path) -> list[str]:
    """Extract all CSV files from a FARS ZIP archive.

    Returns list of extracted filenames.
    """
    extracted = []
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # FARS ZIPs contain CSVs and sometimes a documentation PDF
            if member.lower().endswith(".csv"):
                zf.extract(member, extract_dir)
                extracted.append(member)
                logger.debug("Extracted %s → %s", member, extract_dir)

    logger.info(
        "Extracted %d CSV files from %s", len(extracted), zip_path.name
    )
    return extracted


def _download_with_retry(
    url: str,
    headers: dict[str, str],
) -> httpx.Response:
    """Download a file with retry and exponential backoff.

    FARS files can be 20–100 MB; we use a longer timeout.
    """
    import time

    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=300.0, follow_redirects=True) as client:
                resp = client.get(url, headers=headers)

                if resp.status_code == 304:
                    return resp

                if resp.status_code >= 500:
                    wait = BACKOFF_BASE ** (attempt + 1)
                    logger.warning(
                        "FARS server error %d for %s, retrying in %.1fs",
                        resp.status_code,
                        url,
                        wait,
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code == 404:
                    logger.error("FARS file not found: %s", url)
                    raise RuntimeError(f"FARS file not found: {url}")

                resp.raise_for_status()
                return resp

        except httpx.TimeoutException:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Timeout downloading %s, retrying in %.1fs (attempt %d/%d)",
                url,
                wait,
                attempt + 1,
                MAX_RETRIES,
            )
            time.sleep(wait)

        except httpx.TransportError as exc:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(
                "Transport error downloading %s: %s, retrying in %.1fs",
                url,
                exc,
                wait,
            )
            time.sleep(wait)

    raise RuntimeError(f"Failed to download {url} after {MAX_RETRIES} attempts")
