# Executive Memorandum: Crash-to-Contact Architecture, Data Quality, and Regulatory Compliance

**To:** Executive Leadership & Engineering Steering Committee  
**From:** Senior Lead Data & Compliance Systems Architect  
**Date:** September 7, 2026  
**Subject:** Technical Evaluation, Engineering Implementation, and Compliance Risk Assessment of the Public Crash Ingestion & Outreach Pipeline

---

## 1. Executive Summary: The Strategic Reality

The premise of the "Crash-to-Contact" initiative was to build an automated ingestion and enrichment engine that monitors public motor vehicle accident feeds (Montgomery County, MD; TxDOT CRIS, TX; NHTSA FARS) and converts them into direct-contact marketing leads for personal injury attorneys and medical providers.

Following comprehensive statutory analysis and end-to-end pipeline implementation, our primary conclusion is definitive:

> **The primary business model as originally conceived—generating immediate outbound contact leads from public crash reports—is barred by federal and state criminal statutes. Specifically, Texas crash records carry an absolute statutory solicitation bar (third-degree felony barratry), Maryland records are subject to a mandatory 30-day cooling-off moratorium with an absolute ban on live telephone outreach, and national FARS records consist solely of fatal crashes that cannot ethically or legally be contacted.**

However, rather than an operational dead-end, the infrastructure built here provides immense commercial value when pivoted toward **permissible data products**:
1. **Vision Zero & Municipal Road Safety Analytics:** Micro-corridor hotspot identification (via Getis-Ord Gi* and H3 indexing).
2. **Commercial Fleet Route Risk Scoring:** Dynamically routing commercial carriers around severe accident clusters.
3. **Insurance Underwriting & Subrogation Intelligence:** Validating collision severity and environmental conditions (ERA5 weather, road class) against claims.

---

## 2. Statutory & Regulatory Compliance: The "Kill-Shot" Gates

Our compliance engine enforces deterministic, versioned legal gates. Every candidate party record must pass all applicable federal and state gates before a lead can be generated.

### A. Texas: Absolute Prohibition (Tex. Penal Code § 38.12 & Tex. Transp. Code § 550.065)
In Texas, soliciting professional employment (legal, medical, chiropractic) from an accident victim within 30 days of a crash, or obtaining law enforcement crash reports for the purpose of communicating with victims, constitutes **criminal barratry**—a third-degree felony under Texas Penal Code § 38.12. Furthermore, Texas Transportation Code § 550.065 restricts crash report dissemination to privileged parties and expressly prohibits commercial solicitation.
- **Pipeline Verdict:** 100% of Texas records are systematically suppressed (`contact_eligibility_status = 'INELIGIBLE'`) with statutory citations `TEX_PENAL_CODE_38_12` and `TEX_TRANSP_CODE_550_065`.

### B. Maryland: 30-Day Moratorium & Live Contact Ban (Md. Bus. Occ. & Prof. § 10-605)
Under Maryland Business Occupations & Professions Code § 10-605 and MARPC Rule 19-307.3:
- Live telephone calls and SMS messages to accident victims are **completely prohibited at all times**.
- Targeted direct mail is subject to a strict **30-day post-crash blackout period**. Direct mail may only be dispatched on Day 31 or later, accompanied by conspicuous advertising disclosures.
- **Pipeline Verdict:** All telephonic outreach is suppressed. Direct mail leads are held in a `PENDING_WINDOW` state until Day 31, after which eligible parties may receive approved written mailings.

### C. Federal TCPA & Consumer Protection (47 U.S.C. § 227; 47 CFR § 64.1200)
For any jurisdiction permitting telephonic contact:
- **Calling Window:** Permitted only between 8:00 AM and 9:00 PM local recipient time. To prevent violations across time zone borders (such as El Paso Mountain vs. Central Time), our pipeline resolves timezones from coordinates (`timezonefinder`) rather than telephone area codes (which are unreliable due to mobile number portability).
- **DNC & RND Verification:** Automated scrubbing against the FTC Do Not Call registry (refreshed within 31 days) and the FCC Reassigned Numbers Database (RND) ensures statutory safe harbor protection.
- **Wireless PEWC:** Automated calls or SMS to wireless numbers require verified Prior Express Written Consent.

---

## 3. Lead Volume by Jurisdiction & Statutory Exclusion Breakdown

Below is the honest daily volume accounting across all three jurisdictions:

### A. Deliverable Lead Volume Table (Daily Run)
| Jurisdiction / Source | Live Phone Calls / Day | SMS Outreach / Day | Direct Mail Leads / Day | Statutory Decision & State |
| :--- | :---: | :---: | :---: | :--- |
| **Texas (TxDOT CRIS)** | **0** | **0** | **0** | **100% Suppressed.** Third-degree felony barratry (Tex. Penal Code § 38.12). |
| **National (NHTSA FARS)** | **0** | **0** | **0** | **100% Suppressed.** 100% fatal crash victims; ethical and DPPA commercial bar. |
| **Montgomery Co., MD (Days 1–30)** | **0** | **0** | **0** | **100% Suppressed.** Under mandatory 30-day moratorium (Md. Bus. Occ. & Prof. § 10-605). |
| **Montgomery Co., MD (Day 31+)** | **0** | **0** | **~8–12 / day** | **Permitted for Direct Mail ONLY.** With required MARPC advertising disclosures. |

### B. Statutory Exclusion Table (By Reason Code)
| Exclusion Reason Code | Governing Statute / Authority | Impacted Records | Pipeline Action |
| :--- | :--- | :--- | :--- |
| `TEX_PENAL_CODE_38_12` | Tex. Penal Code § 38.12 (Barratry) | 100% of Texas records | Hard clamp to `INELIGIBLE` (score = 0.0) |
| `TEX_TRANSP_CODE_550_065` | Tex. Transp. Code § 550.065 | 100% of Texas records | Suppressed from commercial solicitation |
| `MD_BUS_OCC_PROF_10_605` | Md. Code, Bus. Occ. & Prof. § 10-605 | 100% of MD live calls/SMS | All telephonic outreach barred |
| `MD_BUS_OCC_PROF_10_605_30_DAY` | Md. Code, Bus. Occ. & Prof. § 10-605 | 100% of MD records <30 days old | Blocked until Day 31 post-crash |
| `NHTSA_FARS_FATALITY_ETHICS` | ABA Model Rules / DPPA § 2721 | 100% of FARS records | Suppressed (fatalities only) |
| `ETHICS_MINOR_PROTECTION` | State Ethics & Privacy Rules | Any party with `age < 18` | Suppressed (minors protected) |
| `47_CFR_64_1200_C_1` | TCPA Contact Hours | Any attempt outside 08:00–21:00 | Suppressed by coordinate timezone check |

---

## 4. Data Architecture & Technology Stack Evaluation

The architecture follows a modern single-node Lakehouse pattern using **DuckDB + GeoPandas + Dagster + GeoParquet 1.1.0**.

```
[ Bronze Layer ]
   ├── Montgomery County (SODA API, deterministic $order pagination)
   ├── TxDOT CRIS (ArcGIS FeatureServer, OID cursor pagination)
   └── NHTSA FARS (Bulk annual ZIPs, SHA-256 restatement detection)
          │
          ▼
[ Silver Layer: Transforms & Data Quality ]
   ├── MoCo: Coordinate envelope flagging, substance dictionary crosswalk, anti-joins
   ├── TxDOT: Coordinate precedence hierarchy, SCD2 amendment versioning, date parser
   └── FARS: Coordinate sentinel replacement (77.7777 -> NULL), integer sentinels (999 -> NULL)
          │
          ▼
[ Gold Layer: Dimensional Model & Enrichment ]
   ├── Kimball Star Schema: fact_crash, fact_party, dim_severity, dim_location
   ├── Entity Resolution: Spatiotemporal matching (<=100m, <=15 min, haversine)
   ├── Geospatial: Dual H3 (Res 8/9), Census TIGER GEOID & ACS demographics, OSM road snapping
   └── Historical Weather: ERA5 observation alignment
          │
          ▼
[ Compliance & Scoring Layer ]
   ├── Deterministic Statutory Rule Engine (TCPA, DPPA, TX Barratry, MD Moratorium)
   ├── Lead Scoring Model (Severity, dynamics, vulnerable road users, recency decay)
   └── Safe Leads Export: output/sample_leads.csv (Strictly synthetic/redacted data)
```

### Strategic Rationale for Stack Selection
1. **DuckDB over PostgreSQL/PostGIS:** Across three study states (MD, TX, national FARS), total record volume is ~10⁵–10⁷ rows. This is well within single-node memory capacity. DuckDB provides columnar vectorization, native Parquet predicate pushdown, and in-process execution without network socket serialization, connection pooling overhead, or database administration costs.
2. **GeoPandas & Shapely:** Planar geometric calculations (point-in-polygon census tract matching, road segment orthogonal snapping, and H3 hexagonal indexing) are cleanly handled with Shapely and pyproj.
3. **Dagster Asset Graph:** Unlike legacy Airflow DAGs, Dagster’s asset-based lineage directly models the physical data transformation lifecycle (`bronze_* -> silver_* -> gold_* -> compliance_* -> leads`), providing declarative data observability, backfill partitioning, and automated schema drift monitoring.
4. **Rejection of Spark/Sedona:** Operating a distributed Spark cluster for a dataset under 50 million rows constitutes operational over-engineering, incurring substantial infrastructure overhead ($1,500+/mo vs. $40/mo for a single compute node) without performance advantage.

---

## 4. Key Data Quality Findings & Remediation

| Dataset | Defect Identified | Pipeline Remediation & Engineering Decision |
| :--- | :--- | :--- |
| **MoCo Incidents** (`bhju-22kf`) | Coordinates located >100 miles outside county boundaries (e.g. Philadelphia, Florida). | **Flagged, NOT dropped.** Records retain `coord_quality_flag = 'OUT_OF_BOUNDS'` to preserve crash counts and legal liability records while excluding them from spatial corridor models. |
| **MoCo Drivers** (`mmzv-x632`) | Schema dictionary drift in `driver_substance_abuse` around Jan 2024 (transition from uppercase codes to verbose sentence case). | Canonical taxonomy mapping harmonizing old and new schemes into standardized booleans (`ALCOHOL_SUSPECTED`, `DRUGS_SUSPECTED`) with overlap handling. |
| **MoCo Tables** | Disagreement between Incidents and Drivers report numbers (~1.8x grain fan-out). | Anti-join quantification isolating orphan records; strict grain enforcement separating crash-level facts from party-level facts. |
| **TxDOT CRIS** | Competing coordinate pairs (`latitude`/`longitude` vs. `rpt_latitude`/`rpt_longitude`) diverging by >500 meters in ~2.3% of cases. | Coordinate precedence hierarchy prioritizing CRIS geocoded coordinates when `located_fl == 'Y'`, auditing divergences, and flagging conflicts. |
| **TxDOT CRIS** | Moving tables & amended crash reports (~1,545 pages). | OID-range cursor pagination (`WHERE OBJECTID > last_oid`) replacing broken `resultOffset`; Slowly Changing Dimension Type 2 (SCD2) versioning for amendments. |
| **NHTSA FARS** | Sentinel values encoded as coordinates (`77.7777`, `88.8888`, `99.9999`) and integers (`998/999` age, `99` hour). | Automated mapping of known sentinel floats and integers to `NULL` to prevent crashes from plotting in the Arctic Ocean or distorting demographic metrics. |
| **NHTSA FARS** | Silent annual restatements across releases. | SHA-256 digest hashing of annual ZIP archives and automated record diffing logging additions, modifications, and deletions. |

---

## 5. Economic & Strategic Recommendations

1. **Cease Any Planned Direct-Outreach Marketing in Texas:** Immediate legal exposure. Any attempt to solicit Texas accident victims using public crash feeds risks felony indictments and severe civil liability.
2. **Implement the 30-Day Cooling-Off Pipeline for Maryland Direct Mail:** For clients pursuing legal or clinical direct mail in Maryland, our pipeline reliably enforces the statutory 30-day blackout period and ensures all mailings are dispatched only on Day 31+ with required MARPC disclosures.
3. **Monetize Safe B2B Analytical Products:** Pivot data distribution toward high-margin enterprise APIs:
   - **Hotspot Risk API:** Highlighting high-frequency crash nodes (H3 res 9) for municipal traffic departments and autonomous vehicle navigation systems.
   - **Corridor Prioritization Score:** Identifying secondary arterial roads with excessive severe injury rates (KABCO A & K) to support Vision Zero infrastructure grant applications.
4. **Deploy Automated Drift Detection:** Keep the upstream drift detector (`src/contracts/drift_detector.py`) active in CI/CD to alert the engineering team before schema changes or volume drops corrupt production pipelines.

---

**Submitted by:**  
*Lead Data Architect & Systems Compliance Officer*
