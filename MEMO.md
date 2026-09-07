# Executive Memorandum: Crash-to-Contact Feasibility, Statutory Lead Analysis, and Architecture

**To:** Executive Leadership & Outbound Operations Steering Committee  
**From:** Senior Lead Data & Compliance Systems Architect  
**Date:** September 7, 2026  
**Subject:** Feasibility Evaluation, Statutory Compliance Analysis, and Deliverable Lead Breakdown for Public Crash Data Pipeline

---

## 1. What Did We Build, and What Did We Deliberately Not Build?

### What We Built:
We built an enterprise-grade, single-node Lakehouse pipeline using **DuckDB**, **GeoPandas**, **GeoParquet 1.1.0**, and **Dagster** that systematically ingests, harmonizes, enriches, and audits motor vehicle crash data across three distinct public sources:
1. **Bronze Ingestion Layer:** High-resolution incremental ingester for Montgomery County, MD SODA REST API (using `$order=report_number` deterministic pagination and durable JSON watermarking), an OID-cursor ingester for Texas TxDOT CRIS ArcGIS FeatureServer (`WHERE OBJECTID > last_oid`), and an annual bulk ZIP ingester for NHTSA FARS with SHA-256 restatement detection.
2. **Silver Transforms & Quality Suite:** Deterministic data quality filters for all 10 documented defects (flagging out-of-bounds coordinates, harmonizing the 2024 substance abuse taxonomy transition, enforcing crash-to-driver grain separation, establishing TxDOT CRIS coordinate precedence, SCD2 amendment versioning, and mapping FARS sentinels to `NULL`).
3. **Gold Dimensional Star Schema:** DuckDB dimensional tables (`fact_crash`, `fact_party`, `dim_location`, `dim_severity`), ANSI D16.1 / KABCO injury severity crosswalk, and cross-source spatiotemporal entity resolution ($\le 100\text{m}$, $\le 15\text{min}$).
4. **Geospatial & TCPA Enrichment:** Dual H3 spatial indexing (Res 8 for neighborhood clustering and Getis-Ord Gi* hotspot detection, Res 9 for intersection-level precision), Census TIGER 11-digit GEOID matching, live ACS 5-year socioeconomic demographic enrichment, OSM roadway snapping, and coordinate-derived IANA timezones (`timezonefinder`).
5. **Deterministic Statutory Compliance Engine:** A versioned rule engine enforcing federal TCPA, DPPA, Texas Barratry, and Maryland 30-day moratorium constraints.

### What We Deliberately Did Not Build:
1. **No Distributed Spark / Sedona Cluster:** At $\sim 10^5 - 10^7$ rows across our study jurisdictions, data fits comfortably in single-node memory. Deploying Spark would introduce unnecessary cloud infrastructure costs ($1,500+/mo vs. $40/mo), network serialization bottlenecks, and cluster maintenance overhead. Spark/Sedona is preserved as our documented scale-out escape hatch for national multi-decade expansion.
2. **No PostgreSQL / PostGIS Concurrent Serving Database:** Unnecessary operational overhead for an analytical lakehouse. DuckDB provides native columnar vectorization and Parquet pushdown without database server administration.
3. **No Automated Live Calling Dialers for Texas or Fatalities:** We deliberately refused to build automated dialers for prohibited jurisdictions where outreach constitutes criminal conduct.

---

## 2. Lead Volume by Jurisdiction & Statutory Exclusion Breakdown

### A. Deliverable Lead Volume Table (Daily Ingestion)
| Jurisdiction / Source | Live Phone Calls / Day | SMS Outreach / Day | Direct Mail Leads / Day | Statutory Status & Governing Authority |
| :--- | :---: | :---: | :---: | :--- |
| **Texas (TxDOT CRIS)** | **0** | **0** | **0** | **100% Suppressed.** Third-degree felony barratry (Tex. Penal Code § 38.12). |
| **National (NHTSA FARS)** | **0** | **0** | **0** | **100% Suppressed.** 100% fatal crash victims; ethical & DPPA commercial bar. |
| **Montgomery Co., MD (Days 1–30)** | **0** | **0** | **0** | **100% Suppressed.** Under mandatory 30-day moratorium (Md. Bus. Occ. & Prof. § 10-605). |
| **Montgomery Co., MD (Day 31+)** | **0** | **0** | **~8–12 / day** | **Permitted for Direct Mail ONLY.** With required MARPC Rule 19-307.3 disclosures. |

### B. Comprehensive Statutory Exclusion Breakdown Table
The exclusion table below accounts for all filtered records across ingestion runs:

| Exclusion Reason Code | Governing Legal Authority | Impacted Records | Pipeline Enforcement Action |
| :--- | :--- | :--- | :--- |
| `TEX_PENAL_CODE_38_12` | Tex. Penal Code § 38.12 (Barratry) | 100% of Texas records | Clamped to `INELIGIBLE` (score = 0.0); blocked indefinitely |
| `TEX_TRANSP_CODE_550_065` | Tex. Transp. Code § 550.065 | 100% of Texas records | Suppressed; crash reports privileged from marketing |
| `MD_BUS_OCC_PROF_10_605` | Md. Code, Bus. Occ. & Prof. § 10-605 | 100% of MD live calls/SMS | All telephonic and electronic outreach prohibited |
| `MD_BUS_OCC_PROF_10_605_30_DAY` | Md. Code, Bus. Occ. & Prof. § 10-605 | 100% of MD records <30 days old | Held in `PENDING_WINDOW` until Day 31 post-crash |
| `NHTSA_FARS_FATALITY_ETHICS` | ABA Model Rules / DPPA § 2721 | 100% of FARS records | Suppressed; marketing to fatal victims/families prohibited |
| `ETHICS_MINOR_PROTECTION` | State Ethics & Privacy Protections | Any party with `age < 18` | Suppressed; minors protected from legal solicitation |
| `47_CFR_64_1200_C_1` | TCPA Permitted Calling Hours | Out-of-window attempts | Suppressed if recipient local time is outside 08:00–21:00 |
| `47_CFR_64_1200_C_2` | National Do Not Call Registry | Registered numbers | Suppressed unless valid consent on file |
| `47_USC_227_B_1_A` | TCPA Wireless Consent | Wireless numbers | Suppressed from automated contact without written PEWC |

---

## 3. Can Records Lawfully Be Delivered to a Live Outbound Call Center?

### The Direct Answer: **NO (Zero deliverable live-call leads across all jurisdictions).**

Here is the legal and statutory reasoning by jurisdiction:

### A. Texas: Third-Degree Felony (Barratry)
Under **Texas Penal Code § 38.12(a)(2)**, soliciting employment (in-person, telephone, or electronic) from an accident victim for economic benefit, or obtaining law enforcement crash reports for the purpose of contacting victims, constitutes **criminal barratry—a third-degree felony**. Crucially, the statute reaches the **individual outbound caller and contact center**, not merely the beneficiary law firm or medical provider. Furthermore, **Tex. Disciplinary Rules of Prof. Conduct 7.03** bars live telephone solicitation, and **Tex. Transp. Code § 550.065** restricts crash reports to privileged parties.
* **Conclusion for Texas:** **Zero contactable leads.** There is no lawful path for live outbound calls.

### B. Maryland: Absolute Live Contact Ban & 30-Day Moratorium
Under **Maryland Business Occupations & Professions Code § 10-605** and **MARPC Rule 19-307.3 (Rule 7.3)**, attorneys and their agents are prohibited from initiating live person-to-person or live telephone contact with accident victims. Direct mail is permissible **only after a mandatory 30-day cooling-off window** has elapsed, and only when accompanied by explicit "Advertising Material" disclosures.
* **Conclusion for Maryland:** **Zero live telephone leads.** Direct mail produces a modest volume (~8–12 leads/day) strictly on Day 31+.

### C. Florida & Other Comparative Jurisdictions
Under **Florida Statutes § 316.066(3)(d)**, knowing commercial misuse of crash reports is a **third-degree felony**. Furthermore, **Rule Regulating the Florida Bar 4-7.18(a)** and **ABA Model Rule 7.3(b)** uniformly prohibit live telephone solicitation of individuals known to need legal services in a specific accident matter.

---

## 4. Viable Product Shapes: Strategic Pivots (One Paragraph Each)

1. **Aggregate Road Safety & Vision Zero Analytics:**  
   By aggregating anonymized crash frequencies and injury severities into H3 hexagonal indices (Res 8/9), we can calculate Getis-Ord Gi* hot spot statistics and Local Moran's I spatial clusters. This creates a high-margin B2G analytics SaaS product for municipal transportation departments, MPOs, and urban planners targeting infrastructure grants for hazardous secondary arterial corridors.

2. **Consented Inbound & Post-Incident Legal Support Portals:**  
   Instead of unlawful outbound telemarketing, the infrastructure can power an inbound educational portal (e.g., automated accident report retrieval, property damage estimation, and insurance rights education). When consumers voluntarily visit the platform and submit a request for assistance with verified Prior Express Written Consent (PEWC), they convert into 100% compliant, high-intent inbound leads.

3. **Enumerated DPPA Non-Solicitation Enterprise Use Cases:**  
   Under 18 U.S.C. § 2721(b) (DPPA permitted uses), verified crash and vehicle data can be lawfully licensed for non-solicitation commercial purposes, including insurance claims validation, subrogation investigation, automotive safety defect tracking, and OEM recall verification.

4. **Commercial Fleet Dynamic Route Hazard Avoidance:**  
   Combining spatial crash density, roadway functional classification, and real-time/historical ERA5 weather conditions allows us to generate dynamic route-risk scores for commercial logistics and telematics providers. Fleet dispatchers can reroute heavy commercial trucks away from high-risk, crash-prone intersections during adverse weather events.

---

## 5. What Would We Build Next, Given a Quarter?

If given a full engineering quarter (12 weeks), we would prioritize:
1. **Statewide Linear Referencing System (LRS) & Road Network Graph:** Ingest statewide DOT roadway centerline shapefiles to enable sub-meter linear referencing (milepoint snapping, intersection approach vs. departure indexing, and AADT traffic volume weighting).
2. **Automated Regulatory & Statutory Monitoring Engine:** Build an automated crawler monitoring state legislative feeds and state bar ethics advisory opinions to flag emerging cooling-off legislation (e.g., changes to state moratorium windows) in real time.
3. **Differential Privacy & Synthetic Safe Data API:** Implement a differential-privacy layer enabling external data consumers to query micro-corridor accident risks without risk of re-identifying involved motorists.
4. **Real-Time Computer-Aided Dispatch (CAD) Streaming Ingestion:** For jurisdictions with open 911 dispatch feeds, build a Kafka/Debezium streaming connector to feed real-time incident notifications into our spatial hazard model within seconds of occurrence.

---

## 6. Where Is the Pipeline Most Likely to Be Wrong, and How Would We Find Out?

1. **Unannounced Upstream Schema & Taxonomy Drift:**  
   * *Where it fails:* Municipalities frequently alter data schemas without notice (e.g., MoCo's 2024 `driver_substance_abuse` transition or Socrata column renames).  
   * *How we detect it:* Our automated upstream drift detector ([src/contracts/drift_detector.py](src/contracts/drift_detector.py)) validates every incoming batch against baseline contracts, immediately triggering alerts on unexpected columns, unmapped category values, null-rate inflation (>10%), or volume collapses (>30%).

2. **Timezone Boundary Edge Cases in Multi-Timezone Jurisdictions:**  
   * *Where it fails:* In border regions (e.g., West Texas spanning Central and Mountain Time), geocoding inaccuracies could cause a crash in Hudspeth County to be assigned Central Time, resulting in premature 8:00 AM contact.  
   * *How we detect it:* We enforce offline coordinate-derived boundary lookups (`timezonefinder`) cross-referenced against Census TIGER county polygons, rejecting any record with ambiguous timezone assignment.

3. **Silent Historical Data Restatements:**  
   * *Where it fails:* NHTSA routinely revises prior-year FARS fatality archives without public changelogs.  
   * *How we detect it:* The pipeline calculates SHA-256 digests on all ingested archives and maintains an automated diff log tracking additions, modifications, and deletions across re-issues.

---

**Submitted by:**  
*Lead Data Architect & Systems Compliance Officer*
