"""
Great Expectations runner — DataFlow EU.

Loads JSON suite definitions from expectations/{bronze,silver,gold}/*.json,
runs them against the warehouse (PostgreSQL or DuckDB), and generates
HTML Data Docs at docs/data-quality/.

Usage:
    python scripts/run_quality_checks.py                  # run all suites
    python scripts/run_quality_checks.py --layer bronze    # run one layer only
    python scripts/run_quality_checks.py --fail-fast       # exit 1 on first failure

Exit code 0 = all expectations passed. Exit code 1 = at least one failed.
Designed to be called from quality_dag.py via Airflow's BashOperator/PythonOperator.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import great_expectations as gx
import structlog
from great_expectations.core.batch import RuntimeBatchRequest
from great_expectations.exceptions import GreatExpectationsError
from sqlalchemy import create_engine

logger = structlog.get_logger(__name__)

EXPECTATIONS_DIR = Path(__file__).parent.parent / "expectations"
DOCS_OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "data-quality"


@dataclass
class SuiteResult:
    suite_name: str
    table: str
    success: bool
    evaluated_expectations: int
    successful_expectations: int
    failed_expectations: list[dict[str, Any]] = field(default_factory=list)


def get_connection_string() -> str:
    """Build the SQLAlchemy connection string from environment variables."""
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "dataflow")
    user = os.environ.get("POSTGRES_USER", "dataflow")
    password = os.environ.get("POSTGRES_PASSWORD", "dataflow")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"


def load_suite_files(layer: str | None = None) -> list[Path]:
    """Find all *_suite.json files, optionally filtered to one layer."""
    layers = [layer] if layer else ["bronze", "silver", "gold"]
    suite_files = []
    for layer_name in layers:
        layer_dir = EXPECTATIONS_DIR / layer_name
        if layer_dir.exists():
            suite_files.extend(sorted(layer_dir.glob("*_suite.json")))
    return suite_files


def run_suite(context: gx.DataContext, suite_path: Path, engine) -> SuiteResult:
    """Load one JSON suite definition and run it against its target table."""
    with suite_path.open() as f:
        suite_def = json.load(f)

    suite_name = suite_def["suite_name"]
    table = suite_def["table"]
    schema, table_name = table.split(".")

    log = logger.bind(suite=suite_name, table=table)
    log.info("suite_started")

    datasource_name = "dataflow_runtime_datasource"
    data_connector_name = "default_runtime_data_connector"
    data_asset_name = table_name

    batch_request = RuntimeBatchRequest(
        datasource_name=datasource_name,
        data_connector_name=data_connector_name,
        data_asset_name=data_asset_name,
        runtime_parameters={"query": f"SELECT * FROM {schema}.{table_name}"},
        batch_identifiers={"default_identifier_name": f"{table_name}_batch"},
    )

    validator = context.get_validator(
        batch_request=batch_request,
        expectation_suite_name=suite_name,
    )

    failed_expectations = []
    successful_count = 0

    for exp in suite_def["expectations"]:
        exp_type = exp["expectation_type"]
        kwargs = {k: v for k, v in exp["kwargs"].items() if not k.startswith("_")}

        try:
            result = getattr(validator, exp_type)(**kwargs)
            if result.success:
                successful_count += 1
            else:
                failed_expectations.append({
                    "expectation_type": exp_type,
                    "kwargs": kwargs,
                    "result": result.result,
                })
                log.warning("expectation_failed", expectation_type=exp_type, kwargs=kwargs)
        except Exception as exc:
            failed_expectations.append({
                "expectation_type": exp_type,
                "kwargs": kwargs,
                "error": str(exc),
            })
            log.error("expectation_errored", expectation_type=exp_type, error=str(exc))

    total = len(suite_def["expectations"])
    success = len(failed_expectations) == 0

    log.info(
        "suite_completed",
        success=success,
        total=total,
        passed=successful_count,
        failed=len(failed_expectations),
    )

    return SuiteResult(
        suite_name=suite_name,
        table=table,
        success=success,
        evaluated_expectations=total,
        successful_expectations=successful_count,
        failed_expectations=failed_expectations,
    )


def generate_html_report(results: list[SuiteResult]) -> Path:
    """Generate a simple, self-contained HTML Data Docs page."""
    DOCS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DOCS_OUTPUT_DIR / "index.html"

    overall_success = all(r.success for r in results)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    rows = ""
    for r in results:
        status_color = "#10b981" if r.success else "#ef4444"
        status_label = "PASSED" if r.success else "FAILED"
        rows += f"""
        <tr>
            <td>{r.suite_name}</td>
            <td><code>{r.table}</code></td>
            <td style="color:{status_color}; font-weight:bold">{status_label}</td>
            <td>{r.successful_expectations} / {r.evaluated_expectations}</td>
        </tr>
        """
        if r.failed_expectations:
            for f in r.failed_expectations:
                rows += f"""
                <tr style="background:#fef2f2">
                    <td colspan="4" style="padding-left: 2rem; font-size: 0.85rem; color: #991b1b">
                        ✗ {f['expectation_type']}({json.dumps(f['kwargs'])})
                    </td>
                </tr>
                """

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DataFlow EU — Data Quality Report</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 2rem auto; color: #1f2937; }}
        h1 {{ color: #111827; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
        th, td {{ text-align: left; padding: 0.6rem; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; }}
        .summary {{ padding: 1rem; border-radius: 8px; background: {"#ecfdf5" if overall_success else "#fef2f2"}; margin-bottom: 1rem; }}
    </style>
</head>
<body>
    <h1>DataFlow EU — Data Quality Report</h1>
    <div class="summary">
        <strong>Overall status:</strong> {"✅ All suites passed" if overall_success else "❌ Some suites failed"}<br>
        <strong>Generated:</strong> {timestamp}
    </div>
    <table>
        <thead>
            <tr><th>Suite</th><th>Table</th><th>Status</th><th>Expectations Passed</th></tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</body>
</html>"""

    output_path.write_text(html)
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Great Expectations suites for DataFlow EU")
    parser.add_argument("--layer", choices=["bronze", "silver", "gold"], help="Run only one layer")
    parser.add_argument("--fail-fast", action="store_true", help="Exit immediately on first failure")
    args = parser.parse_args()

    suite_files = load_suite_files(layer=args.layer)
    if not suite_files:
        logger.warning("no_suites_found", layer=args.layer)
        return 0

    engine = create_engine(get_connection_string())

    context = gx.get_context()
    context.sources.add_or_update_sql(
        name="dataflow_runtime_datasource",
        connection_string=get_connection_string(),
    )

    results: list[SuiteResult] = []

    for suite_path in suite_files:
        try:
            result = run_suite(context, suite_path, engine)
            results.append(result)
            if args.fail_fast and not result.success:
                break
        except GreatExpectationsError as exc:
            logger.error("suite_run_failed", suite_path=str(suite_path), error=str(exc))
            return 1

    report_path = generate_html_report(results)
    logger.info("report_generated", path=str(report_path))

    overall_success = all(r.success for r in results)

    logger.info(
        "quality_check_summary",
        total_suites=len(results),
        passed_suites=sum(1 for r in results if r.success),
        failed_suites=sum(1 for r in results if not r.success),
    )

    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
