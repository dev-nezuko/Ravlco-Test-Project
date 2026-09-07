# Crash-to-Contact: Regulatory-Compliant Public Crash Ingestion & Spatial Analytics Engine

An enterprise-grade, regulatory-compliant data engineering pipeline that ingests, cleans, harmonizes, enriches, and audits motor vehicle accident records from municipal, state, and federal public data sources.

Built with **DuckDB**, **GeoPandas**, **GeoParquet 1.1.0**, **Dagster**, and **Pydantic**.

---

## Architecture Overview

```
                      [ Public Sources ]
     ┌───────────────────────┼───────────────────────┐
     ▼                       ▼                       ▼
Montgomery County, MD   TxDOT CRIS (Texas)       NHTSA FARS (National)
  SODA REST API           ArcGIS FeatureServer     Annual CSV Archives
  ($order cursor)         (OID cursor)             (SHA-256 restatement)
     │                       │                       │
     └───────────────────────┼───────────────────────┘
                             ▼
                   [ Bronze Ingestion ]
          Durable watermarks, raw payload preservation
                             │
                             ▼
                   [ Silver Transforms ]
        Data quality fixes, sentinel replacement, SCD2 versioning
                             │
                             ▼
              [ Gold Dimensional Model (DuckDB) ]
        Kimball Star Schema: fact_crash, fact_party, dim_*
        Cross-source spatiotemporal entity resolution (<=100m, <=15m)
                             │
                             ▼
                  [ Geospatial Enrichment ]
        H3 Indexing (Res 8 & 9), Census TIGER/ACS, Road Snapping, ERA5
                             │
                             ▼
                   [ Compliance Gates ]
        Texas Barratry (Tex. Penal §38.12) -> 100% Suppressed
        Maryland Moratorium (Md. Bus. Occ. §10-605) -> Day 31+ Mail Only
        TCPA (47 U.S.C. §227), DNC Registry, RND Safe Harbor
                             │
                             ▼
                 [ Lead Scoring & Analytics ]
        Multidimensional scoring (0-100) & Getis-Ord Gi* Hotspots
```

---

## Key Findings & Core Compliance Rules

1. **Texas Barratry Kill-Shot:** Under Texas Penal Code § 38.12 and Tex. Transp. Code § 550.065, soliciting accident victims using crash reports is a **third-degree felony**. 100% of Texas records are systematically marked `INELIGIBLE`.
2. **Maryland 30-Day Moratorium:** Under Md. Bus. Occ. & Prof. § 10-605, live telephone outreach is completely prohibited. Direct mail is strictly barred for 30 calendar days following the crash.
3. **TCPA Local Timezone Safety:** Contact hours are strictly 8:00 AM – 9:00 PM recipient local time. To prevent violations across time zone borders (e.g. El Paso Mountain Time), timezones are derived from crash coordinates via `timezonefinder`, not phone area codes.
4. **Data Preservation Over Silent Drops:** Defective records (e.g. coordinates >100 miles outside Montgomery County) are flagged with quality flags rather than silently discarded, preserving total crash counts and legal liability records.

---

## Directory Structure

```
.
├── contracts/                  # Pydantic schema validation contracts
│   ├── bronze_moco.py          # Montgomery County bronze schema contracts
│   ├── bronze_txdot.py         # TxDOT CRIS bronze schema contracts
│   ├── bronze_fars.py          # NHTSA FARS bronze schema contracts
│   └── gold_schema.py          # Gold fact and dimension schema contracts
├── orchestration/              # Workflow definitions
│   └── dagster_definitions.py  # Dagster asset graph, jobs, and schedules
├── output/                     # Exported deliverables
│   └── sample_leads.csv        # Synthetic, fully redacted sample output
├── src/                        # Core application code
│   ├── analysis/               # Spatial statistics
│   │   └── spatial.py          # Getis-Ord Gi* and Local Moran's I (LISA)
│   ├── compliance/             # Statutory compliance rule engine
│   │   ├── ruleset.py          # Abstract rule framework and engine
│   │   ├── eligibility.py      # Party eligibility orchestrator
│   │   └── rules/              # Statutory rule implementations
│   │       ├── barratry.py     # Texas Penal §38.12, Maryland §10-605
│   │       ├── blackout_windows.py # Maryland 30-day moratorium
│   │       ├── contact_channel.py  # TCPA hours, DNC, RND, PEWC, minors
│   │       └── source_gates.py # DPPA, Texas §550.065, FARS ethics
│   ├── contracts/              # Runtime quality contracts
│   │   └── drift_detector.py   # Schema drift and volume anomaly detection
│   ├── geo/                    # Geospatial enrichment
│   │   ├── crs.py              # Projections (EPSG:4326, 5070, 26985, 3081)
│   │   ├── timezone.py         # Coordinate-derived IANA timezones
│   │   ├── h3_index.py         # Dual-resolution H3 indexing (Res 8 & 9)
│   │   ├── census_enrichment.py# TIGER/Line 11-digit GEOID + ACS demographics
│   │   ├── road_snap.py        # Roadway snapping and functional classification
│   │   └── weather_join.py     # ERA5 historical surface weather joining
│   ├── ingestion/              # Bronze layer ingesters
│   │   ├── watermark.py        # Durable atomic-write cursor persistence
│   │   ├── moco_ingester.py    # MoCo Socrata ingester ($order pagination)
│   │   ├── txdot_ingester.py   # TxDOT ArcGIS ingester (OID cursor)
│   │   └── fars_ingester.py    # FARS bulk ZIP ingester (SHA-256 restatements)
│   ├── models/                 # Gold dimensional models
│   │   ├── schema.py           # DuckDB Kimball star schema DDL and loader
│   │   ├── severity_crosswalk.py # ANSI D16.1 / KABCO injury severity crosswalk
│   │   └── entity_resolution.py# Cross-source spatiotemporal deduplication
│   ├── scoring/                # Lead prioritization
│   │   └── lead_score.py       # Multi-factor scoring with compliance hard-gate
│   └── transforms/             # Silver layer data cleaning transforms
│       ├── moco_silver.py      # MoCo quality fixes (bounds, dictionary, grain)
│       ├── txdot_silver.py     # TxDOT quality fixes (precedence, SCD2, dates)
│       └── fars_silver.py      # FARS quality fixes (sentinels, restatement)
├── tests/                      # Automated test suite
│   ├── test_moco_quality.py    # MoCo data quality tests
│   ├── test_txdot_quality.py   # TxDOT data quality tests
│   ├── test_fars_quality.py    # FARS sentinel tests
│   ├── test_gold_models.py     # Gold schema, crosswalk, and entity resolution tests
│   ├── test_geo.py             # Geospatial enrichment tests
│   ├── test_compliance.py      # Statutory compliance tests
│   ├── test_scoring_spatial.py # Lead scoring and spatial hotspot tests
│   └── test_drift_detector.py  # Upstream drift detector tests
├── AI_USE.md                   # AI tooling documentation
├── COMPLIANCE.md               # Legal citations, statutory matrices, and safe harbors
├── DATA_QUALITY.md             # Defect catalog, detection methods, and transforms
├── DECISIONS.md                # Timestamped architectural decision log
├── MEMO.md                     # Executive steering committee memorandum
└── pyproject.toml              # Project dependencies and tool configuration
```

---

## Quickstart & Environment Setup

### 1. Requirements
- Python 3.12+
- macOS / Linux recommended

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/your-org/crash-to-contact.git
cd crash-to-contact

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"
```

### 3. Configuration
Copy the environment example and populate optional API keys:
```bash
cp .env.example .env
```

---

## Running Tests

Execute the comprehensive automated test suite:
```bash
# Run all quality, geospatial, compliance, and scoring tests
pytest tests/ -v
```

---

## Executing the Pipeline

### Running Ingestions
```python
from src.ingestion.moco_ingester import ingest_moco_incidents
from src.ingestion.txdot_ingester import ingest_txdot_crashes
from src.ingestion.fars_ingester import ingest_fars_year

# Incremental fetch with durable watermarks
ingest_moco_incidents(max_records=1000)
ingest_txdot_crashes(max_pages=5)
ingest_fars_year(year=2023)
```

### Launching Dagster Orchestration UI
```bash
dagster dev -f orchestration/dagster_definitions.py
```
Open [http://localhost:3000](http://localhost:3000) to inspect asset lineage and trigger pipeline runs.

---

## Privacy, Compliance, and Data Governance Notice
Per repository governance guidelines:
- **Zero PII:** Real names, phone numbers, addresses, and identifying crash details are strictly excluded from the codebase and version control.
- `output/sample_leads.csv` contains exclusively synthetic, fully redacted data demonstrating compliance decision states.
