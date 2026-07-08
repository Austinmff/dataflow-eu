"""
Bronze loader — reads a partition from S3 (Bronze raw JSON) and loads
it into the corresponding Postgres bronze table (ecb_raw / eurostat_raw).

Idempotent: deletes existing rows for the (year, month) partition before
inserting, so retries and backfill re-runs never duplicate data.
"""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
import psycopg2
import psycopg2.extras
import structlog

logger = structlog.get_logger(__name__)

TABLE_COLUMNS = {
    "ecb": ["source", "series_key", "description", "period", "year", "month", "value", "unit", "extracted_at"],
    "eurostat": ["source", "dataset", "description", "country_code", "year", "month", "value", "unit", "extracted_at"],
}


def _s3_client():
    kwargs: dict[str, Any] = {}
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return boto3.client("s3", **kwargs)


def _pg_conn():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        dbname=os.environ.get("POSTGRES_DB", "dataflow"),
        user=os.environ.get("POSTGRES_USER", "dataflow"),
        password=os.environ.get("POSTGRES_PASSWORD", "dataflow"),
    )


def load_partition(source: str, year: int, month: int) -> dict:
    """Read one S3 partition and load it into bronze.<source>_raw."""
    log = logger.bind(source=source, year=year, month=month)
    bucket = os.environ["S3_BUCKET_NAME"]
    key = f"{source}/year={year}/month={month:02d}/data.json"

    s3 = _s3_client()
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except s3.exceptions.NoSuchKey:
        log.warning("s3_partition_not_found", key=key)
        return {"source": source, "status": "skipped", "reason": "s3_key_missing"}

    payload = json.loads(obj["Body"].read())
    records = payload.get("records", [])
    extracted_at = payload.get("extracted_at")

    if not records:
        log.info("no_records_to_load")
        return {"source": source, "status": "skipped", "reason": "no_records"}

    columns = TABLE_COLUMNS[source]
    table = f"bronze.{source}_raw"

    rows = []
    for r in records:
        row = {col: r.get(col) for col in columns if col != "extracted_at"}
        row["extracted_at"] = extracted_at
        rows.append(tuple(row[col] for col in columns))

    conn = _pg_conn()
    try:
        with conn, conn.cursor() as cur:
            # idempotência: remove a partição antes de recarregar
            cur.execute(f"DELETE FROM {table} WHERE year = %s AND month = %s", (year, month))
            insert_sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
            )
            psycopg2.extras.execute_values(cur, insert_sql, rows)
        log.info("load_complete", row_count=len(rows))
    finally:
        conn.close()

    return {"source": source, "status": "success", "row_count": len(rows)}