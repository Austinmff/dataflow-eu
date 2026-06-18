"""
Extraction Pipeline DAG — DataFlow EU

Orchestrates the ingestion of raw data from Eurostat and ECB APIs
into the Bronze S3 layer (LocalStack in dev, AWS S3 in prod).

Schedule: daily at 06:00 UTC
Catchup: enabled — supports historical backfill from 2019-01-01

Architecture:
    extract_eurostat ──┐
                       ├── notify_success
    extract_ecb     ──┘

Each extract task is idempotent: it checks S3 before calling the API.
On failure, Slack alert is sent via the on_failure_callback.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

from airflow.decorators import dag, task

default_args = {
    "owner": "dataflow-eu",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "email_on_failure": False,
    "email_on_retry": False,
}


def _slack_alert(context: dict) -> None:
    """Send Slack alert on task failure."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        return

    import requests

    dag_id = context["dag"].dag_id
    task_id = context["task_instance"].task_id
    execution_date = context["execution_date"]
    log_url = context["task_instance"].log_url

    message = {
        "text": (
            f":red_circle: *DataFlow EU — Task Failed*\n"
            f"*DAG:* `{dag_id}`\n"
            f"*Task:* `{task_id}`\n"
            f"*Execution date:* `{execution_date}`\n"
            f"*Log:* {log_url}"
        )
    }
    requests.post(webhook_url, json=message, timeout=10)


@dag(
    dag_id="extraction_pipeline",
    description="Ingest raw data from Eurostat and ECB APIs into Bronze S3 layer",
    start_date=datetime(2019, 1, 1),
    schedule_interval="0 6 1 * *",  # 1st of every month at 06:00 UTC
    catchup=True,
    max_active_runs=3,
    default_args=default_args,
    on_failure_callback=_slack_alert,
    tags=["bronze", "extraction", "eurostat", "ecb"],
)
def extraction_pipeline():
    @task(task_id="extract_eurostat")
    def extract_eurostat(logical_date=None, **context) -> dict:
        """
        Extract all Eurostat datasets for the current logical month.
        Skips if partition already exists in S3 (idempotent).
        """
        from extractors.eurostat import EurostatExtractor

        year = logical_date.year
        month = logical_date.month

        extractor = EurostatExtractor()

        if extractor.key_exists(year, month):
            return {
                "source": "eurostat",
                "status": "skipped",
                "reason": "partition_already_exists",
                "year": year,
                "month": month,
            }

        s3_key = extractor.run(year=year, month=month)
        return {
            "source": "eurostat",
            "status": "success",
            "s3_key": s3_key,
            "year": year,
            "month": month,
        }

    @task(task_id="extract_ecb")
    def extract_ecb(logical_date=None, **context) -> dict:
        """
        Extract all ECB series for the current logical month.
        Skips if partition already exists in S3 (idempotent).
        """
        from extractors.ecb import ECBExtractor

        year = logical_date.year
        month = logical_date.month

        extractor = ECBExtractor()

        if extractor.key_exists(year, month):
            return {
                "source": "ecb",
                "status": "skipped",
                "reason": "partition_already_exists",
                "year": year,
                "month": month,
            }

        s3_key = extractor.run(year=year, month=month)
        return {
            "source": "ecb",
            "status": "success",
            "s3_key": s3_key,
            "year": year,
            "month": month,
        }

    @task(task_id="summarize_extraction")
    def summarize_extraction(eurostat_result: dict, ecb_result: dict) -> None:
        """Log a summary of the extraction run for observability."""
        import structlog

        log = structlog.get_logger("extraction_pipeline")
        log.info(
            "extraction_summary",
            eurostat=eurostat_result,
            ecb=ecb_result,
        )

    eurostat = extract_eurostat()
    ecb = extract_ecb()
    summarize_extraction(eurostat, ecb)


extraction_pipeline()
