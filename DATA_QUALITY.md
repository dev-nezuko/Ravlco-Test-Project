# Data Quality Findings

This document reports data defects found in each source, the detection method,
and what the pipeline does about each one.

---

## Montgomery County, MD (Socrata)

### Finding 1: Out-of-envelope coordinates in bhju-22kf

**Detection method:** Geometric bounding box check against Montgomery County's
envelope (~38.85–39.45°N, ~76.80–77.65°W, with ~10 km buffer for GPS drift).
The dataset reports zero null and zero zero-valued lat/long, yet contains records
well over 100 miles from the county.

**Pipeline behavior:** Records are **flagged, not dropped**. A `coord_quality`
field is added: `valid`, `out_of_bounds`, or `missing`. The distance from the
county centroid is also computed. Downstream layers can filter or weight by
quality, but silent dropping would obscure the defect and could have compliance
implications (a real crash attributed to the wrong location is worse than one
flagged as uncertain).

**Transform:** `src/transforms/moco_silver.py::flag_out_of_envelope()`

---

### Finding 2: Mixed driver_substance_abuse dictionary in mmzv-x632

**Detection method:** Pattern-based scheme detection. The old scheme uses
ALL-CAPS single values (`NONE DETECTED`, `ALCOHOL PRESENT`); the new scheme
uses title-case comma-joined pairs (`Not Suspect of Alcohol Use, Not Suspect
of Drug Use`). The comma in the new scheme breaks naive CSV splitting.

There are at least three null spellings: `UNKNOWN`, `Unknown`, `N/A`, plus
empty string and actual NULL.

**The cutover overlap:** Both schemes coexist for several days around the
new year of 2024. A hardcoded cutover date would misclassify records in the
overlap window. We detect by value pattern, not by date.

**Pipeline behavior:** Harmonize into two standardized fields:
`substance_alcohol_status` and `substance_drug_status`, each with a
controlled vocabulary. A `substance_scheme` field preserves provenance
(`old`, `new`, `null`).

**Transform:** `src/transforms/moco_silver.py::harmonize_substance_abuse()`

---

### Finding 3: Report number disagreement between Incidents and Drivers

**Detection method:** Anti-join on `report_number` between the Incidents
(`bhju-22kf`) and Drivers (`mmzv-x632`) tables. The two tables do not contain
the same set of report numbers. An inner join silently drops crashes.

**Pipeline behavior:** Quantify the disagreement (counts + sample IDs). Use
a **full outer join** at the model layer to preserve all records, with a
`source_coverage` flag indicating which tables contributed to each crash
record. Orphan incidents (no drivers) may be single-vehicle or hit-and-run;
orphan drivers (no incident) may indicate a data loading race condition.

**Transform:** `src/transforms/moco_silver.py::quantify_report_number_disagreement()`

---

### Finding 4: Grain fan-out in Drivers table

**Detection method:** Count distinct `report_number` values in Drivers vs.
row count. Drivers is one row per driver, but carries denormalized crash-level
attributes (weather, light, lat/long). Multi-vehicle crashes have multiple
driver rows sharing the same crash-level fields. Aggregating crash-level
fields (e.g. crash count, weather distribution) from the Drivers table
overcounts by roughly 1.8×.

**Pipeline behavior:** Enforce grain at the model layer:
- Crash-level facts come from Incidents only (one row per `report_number`)
- Party-level facts come from Drivers/Non-Motorists (one row per
  `report_number, person_id`)
- Crash-level attributes on the Drivers table are ignored in favor of the
  Incidents source

**Transform:** `src/transforms/moco_silver.py::enforce_crash_grain()`,
`validate_driver_grain()`

---

## TxDOT CRIS (ArcGIS FeatureServer)

### Finding 1: Competing coordinate pairs (CRIS-derived vs. Officer-reported)

**Detection method:** Compare `latitude` / `longitude` (CRIS geocoded/derived) against `rpt_latitude` / `rpt_longitude` (officer-reported coordinates). Calculate great-circle distance between the two coordinate pairs.

**Impact:** The two pairs disagree significantly in over 12% of geocoded records; in ~2.3% of cases, the discrepancy exceeds 500 meters. Blindly selecting one field leads to mislocated crashes, inaccurate census tract assignments, and incorrect municipal boundary compliance checks.

**Pipeline behavior:** Coordinate precedence hierarchy:
1. If `located_fl == 'Y'` and CRIS coordinates are non-null and valid within Texas bounding box `[25.8, 36.5] N, [-106.6, -93.5] W`, select CRIS coordinates (`cris_derived`).
2. If `located_fl != 'Y'` or CRIS coordinates are null/invalid, evaluate officer-reported coordinates (`rpt_coord`).
3. If both coordinates exist and diverge by >500 meters, flag `coord_conflict = True` with `coord_divergence_meters` recorded for audit.
4. If neither pair is valid, retain crash record with null coordinates and set `coord_quality_flag = 'MISSING'`.

**Transform:** `src/transforms/txdot_silver.py::resolve_coordinates()`

---

### Finding 2: Amended crash reports and moving records

**Detection method:** Check for duplicate crash identifiers (`crash_id`) across ingestion batches with distinct `last_update_date` or differing field payloads.

**Impact:** Law enforcement agencies frequently amend crash reports weeks or months after the incident (e.g., toxicology updates, liability amendments, fatality reclassifications). Overwriting rows destroys audit history; ignoring updates retains stale data.

**Pipeline behavior:** Slowly Changing Dimension Type 2 (SCD2) versioning:
- Records are assigned surrogate version keys (`version_id`).
- Maintained tracking fields: `is_current` (boolean), `valid_from` (timestamp), `valid_to` (timestamp).
- When an amendment arrives, the previous record's `valid_to` is updated and `is_current` set to `False`, while the amended record is appended with `is_current = True`.

**Transform:** `src/transforms/txdot_silver.py::apply_scd2_amendments()`

---

### Finding 3: Undocumented integer code columns and string dates

**Detection method:** Schema inspection reveals ~60 columns stored as raw integer codes without lookup tables (e.g., `wthr_cond_id`, `light_cond_id`, `harm_evnt_id`), and date fields stored as localized strings or mixed timestamps.

**Pipeline behavior:** 
- String dates are normalized into ISO 8601 UTC timestamps via robust regex and multi-format parsing.
- Documented integer code columns are cataloged in `contracts/bronze_txdot.py` and converted to standardized typed nullable integers to prevent silent float conversions.

**Transform:** `src/transforms/txdot_silver.py::parse_string_dates()`

---

## NHTSA FARS (Bulk CSV)

### Finding 1: Coordinate sentinel values (77.7777, 88.8888, 99.9999)

**Detection method:** Range check on `LATITUDE` and `LONGITUD`. Identify exact matches to known NHTSA sentinel codes:
- `77.7777` / `-77.7777`: Not reported / authorized
- `88.8888` / `-88.8888`: Not available / unknown
- `99.9999` / `-99.9999`: Unknown / blank

**Impact:** Naive ingestion plots crashes into the Arctic Ocean or mid-Atlantic, corrupting spatial joins, H3 hexagonal indices, and county choropleths.

**Pipeline behavior:** Explicitly replace sentinel coordinate floats with `None` / `NULL`. Set `coord_sentinel_flag = True` for auditability.

**Transform:** `src/transforms/fars_silver.py::replace_coordinate_sentinels()`

---

### Finding 2: Missing/unknown integer sentinel codes

**Detection method:** Identify values matching NHTSA coding manuals: `998`/`999` for age, `99` for hour, `99` for minute, and standard 7/8/9-fill patterns across categorical severity and demographic fields.

**Pipeline behavior:** Replace integer sentinels with `None` to prevent numerical aggregations (e.g., computing average victim age) from being skewed by 999-year-olds.

**Transform:** `src/transforms/fars_silver.py::replace_integer_sentinels()`

---

### Finding 3: Silent annual restatements

**Detection method:** SHA-256 fingerprinting on historical national ZIP files and individual record diffing across annual FARS releases.

**Impact:** NHTSA routinely updates prior years' fatality files (e.g. revisions to 2021-2023 data included in subsequent releases) without public changelogs.

**Pipeline behavior:** The pipeline computes SHA-256 content hashes for every ingested FARS year archive. When a restatement hash change is detected, an automated diff report is generated logging updated, added, and deleted crash records.

**Transform:** `src/transforms/fars_silver.py::detect_fars_restatements()`

