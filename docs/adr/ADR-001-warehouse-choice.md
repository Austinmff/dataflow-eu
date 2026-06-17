# ADR-001: Warehouse Choice — DuckDB (local dev) vs PostgreSQL (production)

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | June 2026                      |
| **Author**  | Austin Manoel Farias Ferreira  |

---

## Context

DataFlow EU requires an analytical warehouse to store the Bronze, Silver, and Gold dbt layers.
The warehouse must:

- Run fully locally without cloud costs during development
- Provide production parity so that dbt models written locally work in staging/prod without changes
- Support the dbt adapters (`dbt-postgres`, `dbt-duckdb`) available for the chosen tools
- Handle 5 years of Eurostat and ECB data (estimated: ~10M rows, < 5 GB uncompressed)

Two serious candidates emerged: **DuckDB** and **PostgreSQL**.

---

## Decision

**Use DuckDB for local development and PostgreSQL 16 for staging and production.**

A `profiles.yml` target switch (`dev` → `prod`) is the only required change between environments.
All dbt models are written in standard SQL compatible with both engines.

---

## Consequences

### Positive

- **DuckDB local dev**: zero infrastructure overhead, sub-second query performance on datasets of this size, native Parquet ingestion directly from Bronze S3 files without a load step.
- **PostgreSQL production**: battle-tested, well-supported in every cloud provider, full support for concurrent writes from multiple Airflow tasks.
- **No model rewrites**: both adapters support the SQL dialect used in this project. Any dialect-specific macro is abstracted behind a dbt macro.
- **Cost**: DuckDB is free and runs in-process. PostgreSQL runs in the Docker Compose stack at zero cost locally.

### Negative

- Maintaining two dbt profiles adds minor configuration overhead.
- DuckDB's concurrency model (single-writer) is irrelevant for local dev but must not be assumed in production — Airflow tasks must not write to DuckDB simultaneously in any future multi-user scenario.
- Integration tests must specify which target they run against.

---

## Alternatives Considered

| Alternative         | Reason Rejected |
|---------------------|-----------------|
| **PostgreSQL only** | Local dev requires running a Docker container even for quick iterations. DuckDB removes this friction and speeds up the inner dev loop significantly. |
| **BigQuery / Snowflake** | Cloud costs and credential management add unnecessary complexity for a portfolio project. Out of scope for v1.0.0. Terraform IaC in `/docs/adr/ADR-005` (future) will cover cloud migration. |
| **SQLite**          | No dbt adapter. Poor analytical query performance. Not suitable for production. |
