# Runbook — DataFlow EU

Operational guide for diagnosing and recovering from pipeline failures.
Written for the "3am page" scenario: assume the reader has no prior context.

---

## Pipeline Overview

```
extraction_pipeline  (06:00 UTC, 1st of month)
        ↓
transformation_pipeline  (08:00 UTC — waits for extraction)
        ↓
quality_pipeline  (09:00 UTC — waits for transformation)
```

Each DAG waits for the previous one via `ExternalTaskSensor`. If one fails, downstream DAGs stay queued (not failed) until the timeout (1 hour) expires.

---

## 1. Extraction failure (`extraction_pipeline`)

### Symptom
Slack alert: `:red_circle: DataFlow EU — Task Failed` with `extract_eurostat` or `extract_ecb`.

### Likely causes & fixes

| Cause | How to confirm | Fix |
|---|---|---|
| Eurostat/ECB API is down | Check Airflow task log for `ConnectionError` or `TimeoutError` after 3 retries | Wait and re-trigger manually; these are public APIs with no SLA |
| API changed response schema | Log shows `ExtractionError: Unexpected ... response structure` | Inspect the raw API response, update `_parse_response()` in the relevant extractor |
| S3/LocalStack unreachable | Log shows `ExtractionError: ... S3 upload failed` | Check `docker compose ps` — is `localstack` healthy? Restart with `docker compose restart localstack` |
| Schema validation failure | Log shows `ValidationError: schema validation failed` | A field is missing or malformed — check the API response against `extractors/schemas/*.json` |

### Manual re-trigger
In the Airflow UI: find the failed task → **Clear** → it re-runs immediately (idempotency check via `key_exists()` prevents duplicate uploads if the partition already succeeded).

### Manual backfill (CLI)
```bash
make backfill DAG=extraction_pipeline START=2023-01-01 END=2023-12-31
```

---

## 2. Transformation failure (`transformation_pipeline`)

### Symptom
Slack alert with `dbt_run_bronze`, `dbt_run_silver`, or `dbt_run_gold`.

### Likely causes & fixes

| Cause | How to confirm | Fix |
|---|---|---|
| dbt model compilation error | Task log shows Jinja/SQL syntax error | Run `make dbt-compile` locally to reproduce before pushing a fix |
| Missing upstream Bronze data | Silver/Gold model returns 0 rows or `ref()` error | Check `extraction_pipeline` succeeded for the same logical date first |
| Schema drift | `on_schema_change: fail` triggers — log shows column mismatch | A source column changed type/name; inspect the raw S3 JSON for that partition, decide whether to update the schema or treat it as a data quality issue |
| PostgreSQL connection refused | Log shows `psycopg2.OperationalError` | Check `docker compose ps` — is `postgres` healthy? Check `.env` credentials match |

### Manual re-trigger
```bash
make dbt-run    # re-runs all models
# or, more targeted:
docker compose exec airflow-webserver dbt run --select tag:silver --profiles-dir /opt/airflow/dbt
```

---

## 3. Quality check failure (`quality_pipeline`)

### Symptom
Slack alert: `:warning: Data Quality Check Failed`, links to `docs/data-quality/index.html`.

### This is the most common "this is actually fine" alert
A failed expectation does **not** mean the pipeline is broken — it means the data looks different than expected. Triage before panicking.

### Triage steps

1. Open `docs/data-quality/index.html` (or re-run locally: `python scripts/run_quality_checks.py`)
2. Find the red row(s) — note the suite name and which expectation failed
3. Cross-reference with the table below

| Failed expectation | Likely meaning | Action |
|---|---|---|
| `expect_table_row_count_to_be_between` (too few rows) | Source API returned partial data, or extraction was skipped | Check `extraction_pipeline` logs for that partition |
| `expect_compound_columns_to_be_unique` (Silver) | Deduplication logic broke, or a genuine duplicate slipped through | Inspect `silver_eurostat`/`silver_ecb` for the flagged keys |
| `expect_column_values_to_be_between` (value out of range) | Either a real economic anomaly (e.g., inflation spike) or a unit conversion bug | Check the raw Bronze value — if real, this is just data, consider widening the range; if wrong, check `_parse_response()` |
| `expect_column_values_to_be_in_set` (Bronze) | API added a new dataset/series code we don't expect | Decide if it's worth onboarding; otherwise it's filtered out downstream anyway |

### Re-run after a fix
```bash
python scripts/run_quality_checks.py --layer silver
```

---

## 4. Dashboard shows no data / stale data

### Symptom
Streamlit dashboard shows "No data found" or numbers haven't updated.

### Checklist

1. **Is the stack running?** `docker compose ps` — confirm `postgres` and `dashboard` are `Up`
2. **Did the pipelines actually run for this month?** Check Airflow UI → DAG run history
3. **Cache**: Streamlit caches queries for 1 hour (`@st.cache_data(ttl=3600)`). Force refresh: click the "⋮" menu in the Streamlit UI → **Clear cache**, or restart: `docker compose restart dashboard`
4. **Connection string wrong?** Check dashboard logs: `docker compose logs dashboard` — look for `OperationalError`

---

## 5. Full stack reset (nuclear option)

When in doubt, or for a clean local demo:

```bash
make clean      # removes all containers AND volumes — all data is lost
make setup      # regenerates .env with fresh keys
make run        # starts fresh
make backfill DAG=extraction_pipeline START=2024-01-01 END=2024-12-31
make dbt-run
python scripts/run_quality_checks.py
```

---

## 6. Who to contact / escalation

This is a solo-maintained portfolio project — there is no on-call rotation. For real production deployments, this section would include:
- PagerDuty/Opsgenie escalation policy
- Secondary on-call contact
- Runbook owner and last-reviewed date

## Appendix: Common log patterns

| Log line contains | Meaning |
|---|---|
| `extraction_started` → `extraction_complete` → no further logs | Task likely hung on validation/upload — check next log line for the relevant task |
| `partition_already_exists` | Idempotency check working as intended — not an error, just a skip |
| `ecb_series_no_data` | ECB API returned 404 for that period — normal for very recent months where data isn't published yet |