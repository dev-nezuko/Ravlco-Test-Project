# Design Decisions

Timestamped log of architectural and design decisions. New entries are appended;
old entries are never deleted, even when reversed.

---

## 2026-09-07 — Stack selection: DuckDB + GeoPandas + Dagster

**Decision:** Use DuckDB (with `spatial` extension) as the primary analytical
engine, GeoPandas for geospatial operations, GeoParquet 1.1.0 for storage, and
Dagster for orchestration.

**Rationale:**

- **DuckDB over Postgres/PostGIS:** At ~10⁵–10⁷ rows across three states, this
  is single-node territory. DuckDB provides columnar analytics, native Parquet
  I/O, and the `spatial` extension for geometry — without server setup or
  operational overhead. The assignment explicitly flags Spark/Sedona as
  over-engineering at this scale.
- **GeoPandas over pure-SQL spatial:** Census tract point-in-polygon joins, road
  network snapping, and H3 indexing are more naturally expressed with Shapely
  geometries than DuckDB SQL. GeoPandas bridges the gap.
- **GeoParquet 1.1.0:** Current stable spec. The `bbox` covering column enables
  row-group pruning. v2.0 is still RC and GeoParquet is incubating OGC, so we
  target 1.1.0.
- **Dagster over Airflow/Prefect:** Asset-based model aligns with our
  bronze→silver→gold→eligibility lineage. Built-in partitioning supports
  date-range backfill. Lightweight local dev.
- **Python 3.12:** Broad library compatibility, required by h3 v4.x and
  timezonefinder 8.x.

**Rejected alternatives:**

- PostgreSQL/PostGIS — unnecessary concurrent serving layer for a batch pipeline.
- Spark/Sedona — correct escape hatch at national multi-year scale, but
  over-engineering for three states. Noted as the scale-out path.
- Airflow — heavier operational burden, DAG-based (not asset-based), less
  natural for data lineage tracking.

---

## 2026-09-07 — CRSS exclusion

**Decision:** Do not ingest or use NHTSA CRSS data.

**Rationale:** CRSS is a probability sample (~50–60k police-reported crashes)
with `WEIGHT` and PSU/stratum design variables. It cannot produce state-level
estimates. Naively unioning it with FARS or MoCo would produce numbers wrong by
orders of magnitude. Since we need record-level crash data for a contact
pipeline — not national estimates — CRSS has no role here.
