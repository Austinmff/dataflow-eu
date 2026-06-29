# ADR-004: Dashboard — Streamlit over Evidence.dev / Metabase / Looker Studio

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | June 2026                      |
| **Author**  | Austin Manoel Farias Ferreira  |

---

## Context

DataFlow EU needed a way to present the Gold layer (`gold_eu_indicators`, `gold_eu_time_series`, `gold_country_comparison`) as an interactive dashboard, runnable locally via Docker Compose alongside the rest of the stack.

Candidates considered: **Streamlit**, **Evidence.dev** (SQL+Markdown static BI), **Metabase** (self-hosted BI tool), **Looker Studio** (Google's free cloud BI tool).

---

## Decision

**Use Streamlit.**

---

## Consequences

### Positive
- **Python-native**: the entire pipeline (extractors, dbt, Great Expectations) is already Python/SQL — Streamlit keeps the whole stack in one language family, no context-switching to a separate templating or config language.
- **Demonstrates a different skill than dbt/SQL alone**: building an interactive frontend (with `st.selectbox`, `st.multiselect`, Plotly charts) shows breadth beyond pure data engineering, which matters for roles that expect engineers to also unblock stakeholders directly.
- **Docker-friendly**: ships as a single container with a `Dockerfile`, fits naturally into the existing `docker-compose.yml` stack with zero new infrastructure paradigms.
- **Fast iteration**: no build step, no separate API layer — `st.cache_data` handles query caching with a one-line decorator.

### Negative
- Streamlit is not a "real" BI tool — no built-in user management, scheduled email reports, or drill-down explore mode that tools like Metabase or Looker Studio provide out of the box.
- Every chart is hand-coded in Python/Plotly rather than configured declaratively; for a dashboard with many more pages, this would become more maintenance-heavy than a proper BI tool's drag-and-drop interface.
- State management (filters, selections) is session-based and resets on refresh — acceptable for a portfolio demo, would need `st.session_state` discipline for a more complex production tool.

---

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| **Evidence.dev** | Excellent fit philosophically (SQL + Markdown, version-controlled BI) but smaller ecosystem/recognition in the PT/ES job market compared to Python skills; would also introduce a new templating language with no other use in the project |
| **Metabase** | Self-hosted BI is a legitimate production pattern, but adds a heavier service (own database, own auth) for a project whose goal is demonstrating the *pipeline*, not operating a BI platform |
| **Looker Studio** | Free and polished, but cloud-only — breaks the "fully local, `make run`, zero external accounts" principle that the rest of this project follows |