"""
Unit tests for BaseExtractor.

Covers the parts of base.py not exercised indirectly through
EurostatExtractor/ECBExtractor tests: run() end-to-end, schema-not-found
path, S3 upload failure, and key_exists() error propagation.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from extractors.base import BaseExtractor, ExtractionError


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bronze-bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")


@pytest.fixture
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-1")
        client.create_bucket(
            Bucket="test-bronze-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        yield client


class DummyExtractor(BaseExtractor):
    """Minimal concrete extractor for testing BaseExtractor itself."""

    source_name = "dummy"
    schema_path = Path("/nonexistent/dummy_schema.json")

    def __init__(self, records=None, raise_on_extract=None):
        super().__init__()
        self._records = records or []
        self._raise_on_extract = raise_on_extract

    def extract(self, year: int, month: int):
        if self._raise_on_extract:
            raise self._raise_on_extract
        return self._records


class TestBaseExtractorRunEndToEnd:
    def test_run_extracts_validates_and_uploads(self, s3_bucket):
        extractor = DummyExtractor(records=[{"id": 1, "value": "x"}])
        extractor._s3_client = s3_bucket

        s3_key = extractor.run(year=2023, month=5)

        assert s3_key == "dummy/year=2023/month=05/data.json"
        obj = s3_bucket.get_object(Bucket="test-bronze-bucket", Key=s3_key)
        assert obj is not None

    def test_run_propagates_extraction_error(self, s3_bucket):
        extractor = DummyExtractor(raise_on_extract=ConnectionError("API down"))
        extractor._s3_client = s3_bucket

        with pytest.raises(ExtractionError):
            extractor.run(year=2023, month=5)


class TestBaseExtractorValidation:
    def test_validate_skips_when_schema_missing(self):
        """schema_path points to a nonexistent file — should warn and return, not raise."""
        extractor = DummyExtractor()
        # Should not raise even though schema file doesn't exist
        extractor._validate([{"anything": "goes"}])


class TestBaseExtractorS3Upload:
    def test_upload_raises_extraction_error_on_client_error(self, s3_bucket):
        extractor = DummyExtractor()
        extractor._s3_client = s3_bucket

        with patch.object(
            s3_bucket,
            "put_object",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject"
            ),
        ):
            with pytest.raises(ExtractionError):
                extractor._upload([{"id": 1}], year=2023, month=5)

    def test_key_exists_raises_on_non_404_client_error(self, s3_bucket):
        extractor = DummyExtractor()
        extractor._s3_client = s3_bucket

        with patch.object(
            s3_bucket,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "HeadObject"
            ),
        ):
            with pytest.raises(ClientError):
                extractor.key_exists(year=2023, month=5)

    def test_s3_client_uses_endpoint_url_when_set(self, monkeypatch):
        monkeypatch.setenv("AWS_ENDPOINT_URL", "http://localhost:4566")
        extractor = DummyExtractor()
        assert extractor.endpoint_url == "http://localhost:4566"


class TestBaseExtractorRetry:
    def test_extract_with_retry_succeeds_first_try(self, s3_bucket):
        extractor = DummyExtractor(records=[{"id": 1}])
        result = extractor._extract_with_retry(year=2023, month=1)
        assert result == [{"id": 1}]

    def test_extract_with_retry_wraps_non_retryable_exception(self):
        extractor = DummyExtractor(raise_on_extract=ValueError("bad data"))
        with pytest.raises(ExtractionError):
            extractor._extract_with_retry(year=2023, month=1)
