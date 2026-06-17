"""
Base extractor class for DataFlow EU pipeline.

All source-specific extractors inherit from BaseExtractor, which provides:
- Retry with exponential backoff (via tenacity)
- Structured JSON logging (via structlog)
- S3 upload to Bronze layer (via boto3)
- JSON Schema validation (via jsonschema)
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3
import jsonschema
import structlog
from botocore.exceptions import ClientError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


class ExtractionError(Exception):
    """Raised when extraction fails after all retries."""


class ValidationError(Exception):
    """Raised when extracted data fails JSON Schema validation."""


class BaseExtractor(ABC):
    """
    Abstract base class for all DataFlow EU extractors.

    Subclasses must implement:
        - source_name (str): unique identifier, used as S3 prefix
        - extract() -> list[dict]: fetch raw records from the source API
        - schema_path (Path): path to the JSON Schema file for validation

    Usage:
        extractor = EurostatExtractor()
        s3_key = extractor.run(year=2023, month=1)
    """

    def __init__(self) -> None:
        self.bucket = os.environ["S3_BUCKET_NAME"]
        self.endpoint_url = os.environ.get("AWS_ENDPOINT_URL")  # None in prod
        self._s3_client = None

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Unique source identifier. Used as the S3 prefix."""

    @property
    @abstractmethod
    def schema_path(self) -> Path:
        """Absolute path to the JSON Schema file for this source."""

    @abstractmethod
    def extract(self, year: int, month: int) -> list[dict[str, Any]]:
        """
        Fetch raw records from the source API for a given year/month.

        Returns a list of dicts, each representing one record.
        Raise ExtractionError on unrecoverable failure.
        """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, year: int, month: int) -> str:
        """
        Full pipeline for one partition: extract → validate → upload.

        Returns the S3 key where the data was stored.
        """
        log = logger.bind(source=self.source_name, year=year, month=month)
        log.info("extraction_started")

        records = self._extract_with_retry(year=year, month=month)
        log.info("extraction_complete", record_count=len(records))

        self._validate(records)
        log.info("validation_passed")

        s3_key = self._upload(records, year=year, month=month)
        log.info("upload_complete", s3_key=s3_key)

        return s3_key

    # ------------------------------------------------------------------
    # Retry wrapper
    # ------------------------------------------------------------------

    def _extract_with_retry(self, year: int, month: int) -> list[dict[str, Any]]:
        @retry(
            retry=retry_if_exception_type((ConnectionError, TimeoutError)),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        def _inner() -> list[dict[str, Any]]:
            return self.extract(year=year, month=month)

        try:
            return _inner()
        except Exception as exc:
            raise ExtractionError(
                f"[{self.source_name}] extraction failed for {year}-{month:02d}"
            ) from exc

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, records: list[dict[str, Any]]) -> None:
        if not self.schema_path.exists():
            logger.warning("schema_not_found", path=str(self.schema_path))
            return

        with self.schema_path.open() as f:
            schema = json.load(f)

        payload = {"records": records}
        try:
            jsonschema.validate(instance=payload, schema=schema)
        except jsonschema.ValidationError as exc:
            raise ValidationError(
                f"[{self.source_name}] schema validation failed: {exc.message}"
            ) from exc

    # ------------------------------------------------------------------
    # S3 upload
    # ------------------------------------------------------------------

    @property
    def s3(self) -> boto3.client:
        if self._s3_client is None:
            kwargs: dict[str, Any] = {}
            if self.endpoint_url:
                kwargs["endpoint_url"] = self.endpoint_url
            self._s3_client = boto3.client("s3", **kwargs)
        return self._s3_client

    def _s3_key(self, year: int, month: int) -> str:
        """
        Partition path following Hive-style conventions.
        Example: eurostat/year=2023/month=01/data.json
        """
        return f"{self.source_name}/year={year}/month={month:02d}/data.json"

    def _upload(self, records: list[dict[str, Any]], year: int, month: int) -> str:
        key = self._s3_key(year, month)
        payload = {
            "source": self.source_name,
            "extracted_at": datetime.utcnow().isoformat(),
            "year": year,
            "month": month,
            "record_count": len(records),
            "records": records,
        }
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

        try:
            self.s3.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=BytesIO(body),
                ContentType="application/json",
            )
        except ClientError as exc:
            raise ExtractionError(
                f"[{self.source_name}] S3 upload failed for key {key}"
            ) from exc

        return key

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def key_exists(self, year: int, month: int) -> bool:
        """Return True if this partition already exists in S3 (idempotency check)."""
        key = self._s3_key(year, month)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise
