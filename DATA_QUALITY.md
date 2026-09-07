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

*Findings to be added after TxDOT silver transforms are implemented.*

---

## NHTSA FARS (Bulk CSV)

*Findings to be added after FARS silver transforms are implemented.*
