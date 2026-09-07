"""Durable watermark / cursor persistence for incremental ingestion.

Each ingester stores its progress in a JSON state file under data/state/.
On restart, the ingester reads this state to resume from where it left off,
avoiding duplicate fetches.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATE_DIR = Path("data/state")


class Watermark:
    """Manages durable ingestion state for a single source/dataset.

    State is persisted as a JSON file at ``data/state/{source_id}.json``.
    Fields are source-specific but always include ``last_updated`` (ISO-8601 UTC)
    and ``content_hash`` (SHA-256 of last-seen payload for restatement detection).

    Usage::

        wm = Watermark("moco_bhju-22kf")
        cursor = wm.get("last_offset", default=0)
        # ... fetch data ...
        wm.set("last_offset", new_offset)
        wm.save()
    """

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        self._path = STATE_DIR / f"{source_id}.json"
        self._state: dict[str, Any] = {}
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, key: str, *, default: Any = None) -> Any:
        """Read a value from the persisted state."""
        return self._state.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Stage a value for persistence. Call ``save()`` to flush to disk."""
        self._state[key] = value

    def save(self) -> None:
        """Atomically write state to disk.

        Uses write-to-temp + rename for crash safety.
        """
        self._state["last_updated"] = datetime.now(timezone.utc).isoformat()
        self._path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._state, indent=2, default=str))
        tmp_path.rename(self._path)
        logger.info("Watermark saved for %s", self.source_id)

    def is_fresh(self) -> bool:
        """Return True if any state has been persisted previously."""
        return "last_updated" in self._state

    # ── Helpers ───────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load existing state from disk, if present."""
        if self._path.exists():
            try:
                self._state = json.loads(self._path.read_text())
                logger.info(
                    "Loaded watermark for %s (last_updated=%s)",
                    self.source_id,
                    self._state.get("last_updated", "unknown"),
                )
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Corrupt watermark for %s, starting fresh: %s",
                    self.source_id,
                    exc,
                )
                self._state = {}

    @staticmethod
    def content_hash(data: bytes) -> str:
        """SHA-256 hex digest of raw content for restatement detection."""
        return hashlib.sha256(data).hexdigest()

    def __repr__(self) -> str:
        return f"Watermark({self.source_id!r}, fresh={self.is_fresh()})"
