# AI Usage Log

This document records where AI assistance was used during the development of
this project, per the assignment's ground rules.

## Format

Each entry notes the task, the tool used, and what the AI contributed versus
what was human-directed.

---

## Entries

### 2026-09-07 — Project scaffold and implementation planning

- **Tool:** Antigravity (Claude Opus 4.6)
- **Task:** Reading the assignment, structuring the implementation plan, generating
  the project scaffold (directory structure, `pyproject.toml`, `.gitignore`).
- **AI contribution:** Generated boilerplate file structure and dependency list.
  Implementation plan was collaboratively refined from human's initial understanding.
- **Human contribution:** Provided high-level architectural understanding, confirmed
  the correct end-state (zero contactable leads), approved the plan.

---

### 2026-09-07 — Bronze Ingestion & Watermarking

- **Tool:** Antigravity (Claude Opus 4.6)
- **Task:** Designing durable watermark engine and three custom ingesters (MoCo Socrata, TxDOT ArcGIS, FARS bulk).
- **AI contribution:** Implemented atomic write state manager, `$order`-based deterministic pagination, OID cursor pagination, and SHA-256 restatement detection.
- **Human contribution:** Directed separation of concerns and commit cadence requirements per AGENTS.md.

---

### 2026-09-07 — Silver Transforms & Data Quality Suite

- **Tool:** Antigravity (Claude Opus 4.6 / Gemini 3.8 Flash)
- **Task:** Implementing silver transforms for coordinate bounds, dictionary drift, anti-joins, SCD2 amendments, and FARS sentinels.
- **AI contribution:** Generated transform logic and corresponding pytest test suites for all 10 documented defect types.
- **Human contribution:** Guided prioritization of data preservation (flagging over silent dropping) and legal citation documentation.

---

### 2026-09-07 — Gold Dimensional Model & Geospatial Enrichment

- **Tool:** Antigravity (Gemini 3.8 Flash)
- **Task:** Star schema DDL, KABCO severity crosswalk, entity resolution, CRS reprojections, H3 indexing, and Census demographic enrichment.
- **AI contribution:** Implemented Kimball fact/dimension schemas, haversine clustering, timezonefinder local time derivation, and TIGER/Line GEOID matching.
- **Human contribution:** Reviewed schema definitions and approved the dual H3 resolution strategy (res 8 & 9).

---

### 2026-09-07 — Compliance Engine & Lead Scoring

- **Tool:** Antigravity (Gemini 3.8 Flash)
- **Task:** Developing statutory compliance gates, TCPA checks, Texas barratry suppressions, Maryland moratorium rules, and priority lead scoring.
- **AI contribution:** Created modular rule engine with statutory citation tracking, Getis-Ord Gi* hotspot statistics, and synthetic sample output generator.
- **Human contribution:** Mandated strict statutory adherence for Texas Penal Code § 38.12 and Maryland Bus. Occ. & Prof. § 10-605.

