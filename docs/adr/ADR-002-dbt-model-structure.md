# ADR-002: dbt Model Structure — Medallion Architecture over Subject-Area

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | June 2026                      |
| **Author**  | Austin Manoel Farias Ferreira  |

---

## Context

dbt projects need a folder/layering convention. Two common patterns:

1. **Medallion Architecture** (Bronze/Silver/Gold) — organizes models by *data maturity*
2. **Subject-area / Kimball-style** (staging/intermediate/marts, organized by business domain) — organizes models by *business subject*

DataFlow EU ingests from only two sources (Eurostat, ECB) feeding a single business domain (EU economic indicators), so the choice mattered less for "scale" reasons and more for **what a hiring manager in Portugal/Spain expects to see**.

---

## Decision

**Use Medallion Architecture: `bronze/`, `silver/`, `gold/`.**

- **Bronze**: thin views over raw staging tables, no transformation, immutable
- **Silver**: cleaned, typed, deduplicated, one model per source
- **Gold**: business-ready tables joined across sources, optimized for the dashboard's exact query patterns

---

## Consequences

### Positive
- Medallion is the dominant pattern referenced in Databricks/Azure/Microsoft Fabric job postings across the EU market — using this terminology directly in the project signals familiarity with tooling recruiters search for.
- Clear mental model: "is this immutable raw data, cleaned data, or business-ready data?" maps directly to a folder.
- Materialization strategy follows naturally: Bronze=view (cheap, always fresh), Silver=incremental (avoid reprocessing years of history), Gold=table (fast dashboard reads).

### Negative
- With only 2 sources, the separation between Silver and Gold can feel like overhead for a project this size — a `marts/` folder alone might have sufficed.
- If DataFlow EU grows to 10+ sources across distinct business domains (e.g., adding a fully separate "labor market" vs "trade" domain), a hybrid medallion + subject-area structure (`gold/economic/`, `gold/trade/`) would likely be needed.

---

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| **Kimball staging/marts** | Less recognizable terminology in EU job postings; adds folder depth without benefit at this scale |
| **Flat structure (all models in one folder)** | No clear maturity signal; harder to apply different materialization configs by folder in `dbt_project.yml` |