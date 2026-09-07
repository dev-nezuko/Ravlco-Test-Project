"""Harmonization of crash and injury severity to national KABCO standard.

References:
- ANSI D16.1-2017: Manual on Classification of Motor Vehicle Traffic Accidents
- FHWA Safety Performance Management Measures (23 CFR Part 490)
- Model Minimum Uniform Crash Criteria (MMUCC) 5th Edition

KABCO Standard Scale:
  K - Fatal Injury (Killed)
  A - Suspected Serious Injury (Incapacitating)
  B - Suspected Minor Injury (Non-incapacitating evident injury)
  C - Possible Injury (Complaint of pain, no visible injury)
  O - No Apparent Injury (Property Damage Only / Uninjured)
  U - Unknown / Not Reported
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class KABCOSeverity(str, Enum):
    """Standardized KABCO injury severity levels."""

    FATAL = "K"
    SUSPECTED_SERIOUS = "A"
    SUSPECTED_MINOR = "B"
    POSSIBLE_INJURY = "C"
    NO_INJURY = "O"
    UNKNOWN = "U"

    @property
    def rank(self) -> int:
        """Ordinal rank for severity comparisons (higher = more severe)."""
        ranks = {
            "K": 5,
            "A": 4,
            "B": 3,
            "C": 2,
            "O": 1,
            "U": 0,
        }
        return ranks[self.value]

    @property
    def label(self) -> str:
        labels = {
            "K": "Fatal Injury (Killed)",
            "A": "Suspected Serious Injury",
            "B": "Suspected Minor Injury",
            "C": "Possible Injury",
            "O": "No Apparent Injury",
            "U": "Unknown / Not Reported",
        }
        return labels[self.value]


# ── Montgomery County, MD mapping ──────────────────────────────────────────
# MoCo Incident/Driver table injury_severity strings:
MOCO_SEVERITY_MAP: dict[str, KABCOSeverity] = {
    "FATAL INJURY": KABCOSeverity.FATAL,
    "FATALITY": KABCOSeverity.FATAL,
    "FATAL": KABCOSeverity.FATAL,
    "SUSPECTED SERIOUS INJURY": KABCOSeverity.SUSPECTED_SERIOUS,
    "INCAPACITATING INJURY": KABCOSeverity.SUSPECTED_SERIOUS,
    "SEVERE INJURY": KABCOSeverity.SUSPECTED_SERIOUS,
    "SUSPECTED MINOR INJURY": KABCOSeverity.SUSPECTED_MINOR,
    "NON-INCAPACITATING INJURY": KABCOSeverity.SUSPECTED_MINOR,
    "MINOR INJURY": KABCOSeverity.SUSPECTED_MINOR,
    "POSSIBLE INJURY": KABCOSeverity.POSSIBLE_INJURY,
    "NO APPARENT INJURY": KABCOSeverity.NO_INJURY,
    "PROPERTY DAMAGE ONLY": KABCOSeverity.NO_INJURY,
    "NONE": KABCOSeverity.NO_INJURY,
    "UNKNOWN": KABCOSeverity.UNKNOWN,
    "N/A": KABCOSeverity.UNKNOWN,
}

# ── Texas TxDOT CRIS mapping ──────────────────────────────────────────────
# TxDOT CRIS uses crash_sev_id or injury_severity code:
# 1 = Killed (K)
# 2 = Suspected Serious Injury (A)
# 3 = Non-incapacitating Injury (B)
# 4 = Possible Injury (C)
# 5 = Non-injury (O)
# 0 / 99 = Unknown (U)
TXDOT_SEVERITY_CODE_MAP: dict[Any, KABCOSeverity] = {
    1: KABCOSeverity.FATAL,
    "1": KABCOSeverity.FATAL,
    "K": KABCOSeverity.FATAL,
    "KILLED": KABCOSeverity.FATAL,
    "FATAL": KABCOSeverity.FATAL,
    2: KABCOSeverity.SUSPECTED_SERIOUS,
    "2": KABCOSeverity.SUSPECTED_SERIOUS,
    "A": KABCOSeverity.SUSPECTED_SERIOUS,
    "INCAPACITATING": KABCOSeverity.SUSPECTED_SERIOUS,
    "SUSPECTED SERIOUS": KABCOSeverity.SUSPECTED_SERIOUS,
    3: KABCOSeverity.SUSPECTED_MINOR,
    "3": KABCOSeverity.SUSPECTED_MINOR,
    "B": KABCOSeverity.SUSPECTED_MINOR,
    "NON-INCAPACITATING": KABCOSeverity.SUSPECTED_MINOR,
    "SUSPECTED MINOR": KABCOSeverity.SUSPECTED_MINOR,
    4: KABCOSeverity.POSSIBLE_INJURY,
    "4": KABCOSeverity.POSSIBLE_INJURY,
    "C": KABCOSeverity.POSSIBLE_INJURY,
    "POSSIBLE": KABCOSeverity.POSSIBLE_INJURY,
    5: KABCOSeverity.NO_INJURY,
    "5": KABCOSeverity.NO_INJURY,
    "O": KABCOSeverity.NO_INJURY,
    "NON-INJURY": KABCOSeverity.NO_INJURY,
    "NOT INJURED": KABCOSeverity.NO_INJURY,
    0: KABCOSeverity.UNKNOWN,
    "0": KABCOSeverity.UNKNOWN,
    99: KABCOSeverity.UNKNOWN,
    "99": KABCOSeverity.UNKNOWN,
    "U": KABCOSeverity.UNKNOWN,
    "UNKNOWN": KABCOSeverity.UNKNOWN,
}

# ── NHTSA FARS mapping ───────────────────────────────────────────────────
# FARS INJ_SEV codes:
# 0 = No Apparent Injury (O)
# 1 = Possible Injury (C)
# 2 = Suspected Minor Injury (B)
# 3 = Suspected Serious Injury (A)
# 4 = Fatal Injury (K)
# 5 = Injured, Severity Unknown (U)
# 6 = Died Prior to Crash (Excluded or U)
# 9 = Unknown (U)
FARS_INJ_SEV_MAP: dict[Any, KABCOSeverity] = {
    4: KABCOSeverity.FATAL,
    "4": KABCOSeverity.FATAL,
    "K": KABCOSeverity.FATAL,
    3: KABCOSeverity.SUSPECTED_SERIOUS,
    "3": KABCOSeverity.SUSPECTED_SERIOUS,
    "A": KABCOSeverity.SUSPECTED_SERIOUS,
    2: KABCOSeverity.SUSPECTED_MINOR,
    "2": KABCOSeverity.SUSPECTED_MINOR,
    "B": KABCOSeverity.SUSPECTED_MINOR,
    1: KABCOSeverity.POSSIBLE_INJURY,
    "1": KABCOSeverity.POSSIBLE_INJURY,
    "C": KABCOSeverity.POSSIBLE_INJURY,
    0: KABCOSeverity.NO_INJURY,
    "0": KABCOSeverity.NO_INJURY,
    "O": KABCOSeverity.NO_INJURY,
    5: KABCOSeverity.UNKNOWN,
    "5": KABCOSeverity.UNKNOWN,
    6: KABCOSeverity.UNKNOWN,
    "6": KABCOSeverity.UNKNOWN,
    9: KABCOSeverity.UNKNOWN,
    "9": KABCOSeverity.UNKNOWN,
    "U": KABCOSeverity.UNKNOWN,
}


def crosswalk_severity(raw_value: Any, source_jurisdiction: str) -> KABCOSeverity:
    """Map raw severity from any source into standard KABCO scale.

    Parameters
    ----------
    raw_value:
        Raw string or numeric code from source system.
    source_jurisdiction:
        One of 'moco', 'txdot', 'fars'.

    Returns
    -------
    KABCOSeverity enum value.
    """
    if raw_value is None:
        return KABCOSeverity.UNKNOWN

    jurisdiction = source_jurisdiction.lower().strip()

    if jurisdiction == "moco":
        cleaned = str(raw_value).strip().upper()
        return MOCO_SEVERITY_MAP.get(cleaned, KABCOSeverity.UNKNOWN)

    elif jurisdiction == "txdot":
        # Check direct lookup (handles both int and str)
        if raw_value in TXDOT_SEVERITY_CODE_MAP:
            return TXDOT_SEVERITY_CODE_MAP[raw_value]
        cleaned = str(raw_value).strip().upper()
        return TXDOT_SEVERITY_CODE_MAP.get(cleaned, KABCOSeverity.UNKNOWN)

    elif jurisdiction == "fars":
        if raw_value in FARS_INJ_SEV_MAP:
            return FARS_INJ_SEV_MAP[raw_value]
        cleaned = str(raw_value).strip().upper()
        return FARS_INJ_SEV_MAP.get(cleaned, KABCOSeverity.UNKNOWN)

    # Generic fallback
    s = str(raw_value).strip().upper()
    if s in ("K", "FATAL", "FATALITY"):
        return KABCOSeverity.FATAL
    if s in ("A", "SERIOUS", "INCAPACITATING"):
        return KABCOSeverity.SUSPECTED_SERIOUS
    if s in ("B", "MINOR"):
        return KABCOSeverity.SUSPECTED_MINOR
    if s in ("C", "POSSIBLE"):
        return KABCOSeverity.POSSIBLE_INJURY
    if s in ("O", "NO INJURY", "PROPERTY DAMAGE"):
        return KABCOSeverity.NO_INJURY

    return KABCOSeverity.UNKNOWN


def aggregate_crash_severity(party_severities: list[KABCOSeverity]) -> KABCOSeverity:
    """Determine crash-level severity from highest party-level severity.

    Following ANSI D16.1, a crash's overall severity is defined by the most
    severe injury suffered by any person involved in the crash.
    """
    if not party_severities:
        return KABCOSeverity.UNKNOWN
    return max(party_severities, key=lambda s: s.rank)
