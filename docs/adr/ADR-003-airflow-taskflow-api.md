# ADR-003: Airflow TaskFlow API over Classic Operators

| Field       | Value                          |
|-------------|--------------------------------|
| **Status**  | Accepted                       |
| **Date**    | June 2026                      |
| **Author**  | Austin Manoel Farias Ferreira  |

---

## Context

Airflow 2.x offers two ways to define DAGs:

1. **Classic operators** (`PythonOperator`, `BashOperator`, explicit `set_upstream`/`set_downstream`)
2. **TaskFlow API** (`@dag`/`@task` decorators, implicit dependencies via function calls, automatic XCom passing)

All three DAGs in this project (`extraction_pipeline`, `transformation_pipeline`, `quality_pipeline`) needed to pass small pieces of state between tasks (e.g., extraction result metadata into a summary task).

---

## Decision

**Use the TaskFlow API (`@dag`, `@task`) for all DAGs in this project.**

```python
@task(task_id="extract_eurostat")
def extract_eurostat(logical_date=None, **context) -> dict:
    ...
    return {"source": "eurostat", "status": "success", ...}

eurostat = extract_eurostat()
ecb = extract_ecb()
summarize_extraction(eurostat, ecb)  # dependency is implicit
```

---

## Consequences

### Positive
- **Implicit dependencies**: passing `eurostat` and `ecb` directly into `summarize_extraction()` both creates the task dependency *and* passes the return value via XCom — no manual `xcom_pull()` calls.
- **Plain Python functions**: easier to unit test in isolation outside of Airflow (a function decorated with `@task` is still callable directly in tests).
- **Less boilerplate**: no need for explicit `>>` chains when dependencies are derivable from function calls.
- This is Airflow's own recommended modern style since 2.0 — using it signals current best practices rather than legacy patterns.

### Negative
- TaskFlow still requires classic operators where no Python-native equivalent exists — `ExternalTaskSensor` in `transformation_pipeline` and `quality_pipeline` is a classic operator, mixed with `@task`-decorated functions in the same DAG. This hybrid style needs both patterns understood.
- XCom payloads are implicitly serialized; large objects passed between tasks (e.g., full dataframes) would silently bloat the metadata DB. Mitigated here because we deliberately pass small summary dicts, not full records, between tasks.

---

## Alternatives Considered

| Alternative | Reason Rejected |
|---|---|
| **Classic `PythonOperator` + explicit XCom** | More boilerplate for the same outcome; no longer Airflow's recommended pattern |
| **Pure `BashOperator` shelling out to scripts** | Loses Python-native testability and type hints; harder to unit test the orchestration logic itself |