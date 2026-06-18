"""
Unit tests for EurostatExtractor.

Uses moto to mock S3 — no real AWS or LocalStack required.
Uses responses/pytest-mock to mock the Eurostat HTTP API.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_EUROSTAT_RESPONSE = {
    "version": "2.0",
    "label": "GDP per capita",
    "value": {
        "0": 32500.0,
        "1": 45100.0,
        "2": None,
    },
    "dimension": {
        "geo": {
            "label": "Country",
            "category": {
                "index": {"PT": 0, "DE": 1, "ES": 2},
                "label": {"PT": "Portugal", "DE": "Germany", "ES": "Spain"},
            },
        },
        "time": {
            "label": "Time",
            "category": {
                "index": {"2023": 0},
                "label": {"2023": "2023"},
            },
        },
    },
}


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set required environment variables for every test."""
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bronze-bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")  # empty = use moto
    monkeypatch.setenv("EUROSTAT_BASE_URL", "https://fake-eurostat.eu/api")


@pytest.fixture
def s3_bucket():
    """Create a mocked S3 bucket for tests."""
    with mock_aws():
        client = boto3.client("s3", region_name="eu-west-1")
        client.create_bucket(
            Bucket="test-bronze-bucket",
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"},
        )
        yield client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestEurostatExtractorParsing:
    def test_parse_response_returns_flat_records(self):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        meta = {"description": "GDP per capita", "unit": "CP_EUR_HAB"}
        records = extractor._parse_response(
            FAKE_EUROSTAT_RESPONSE, "nama_10_pc", meta, year=2023, month=1
        )

        assert len(records) == 3
        pt = next(r for r in records if r["country_code"] == "PT")
        assert pt["value"] == 32500.0
        assert pt["dataset"] == "nama_10_pc"
        assert pt["year"] == 2023
        assert pt["month"] == 1

    def test_parse_response_handles_null_values(self):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        meta = {"description": "GDP per capita", "unit": "CP_EUR_HAB"}
        records = extractor._parse_response(
            FAKE_EUROSTAT_RESPONSE, "nama_10_pc", meta, year=2023, month=1
        )

        es = next(r for r in records if r["country_code"] == "ES")
        assert es["value"] is None

    def test_parse_response_empty_value_map(self):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        meta = {"description": "GDP per capita", "unit": "CP_EUR_HAB"}
        empty_response = {**FAKE_EUROSTAT_RESPONSE, "value": {}}
        records = extractor._parse_response(empty_response, "nama_10_pc", meta, year=2023, month=1)
        assert records == []

    def test_skip_annual_dataset_for_non_january(self):
        """Annual datasets should only be extracted in January."""
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        with patch.object(extractor, "_fetch_dataset") as mock_fetch:
            mock_fetch.return_value = FAKE_EUROSTAT_RESPONSE
            records = extractor.extract(year=2023, month=6)

        # nama_10_pc and demo_pjan should be skipped for month=6
        datasets_fetched = {r["dataset"] for r in records}
        assert "nama_10_pc" not in datasets_fetched
        assert "demo_pjan" not in datasets_fetched


class TestEurostatExtractorS3:
    def test_s3_key_format(self):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        key = extractor._s3_key(year=2023, month=3)
        assert key == "eurostat/year=2023/month=03/data.json"

    def test_upload_writes_to_s3(self, s3_bucket):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        extractor._s3_client = s3_bucket  # inject mocked client

        records = [
            {
                "source": "eurostat",
                "dataset": "une_rt_m",
                "country_code": "PT",
                "year": 2023,
                "month": 3,
                "value": 6.5,
                "unit": "PC_ACT",
                "description": "Unemployment rate",
            }
        ]

        key = extractor._upload(records, year=2023, month=3)

        obj = s3_bucket.get_object(Bucket="test-bronze-bucket", Key=key)
        body = json.loads(obj["Body"].read())

        assert body["source"] == "eurostat"
        assert body["record_count"] == 1
        assert body["records"][0]["value"] == 6.5

    def test_key_exists_returns_false_for_missing(self, s3_bucket):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        extractor._s3_client = s3_bucket

        assert extractor.key_exists(year=2023, month=3) is False

    def test_key_exists_returns_true_after_upload(self, s3_bucket):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        extractor._s3_client = s3_bucket

        records = [
            {
                "source": "eurostat",
                "dataset": "une_rt_m",
                "country_code": "PT",
                "year": 2023,
                "month": 3,
                "value": 6.5,
                "unit": "PC_ACT",
                "description": "Unemployment rate",
            }
        ]
        extractor._upload(records, year=2023, month=3)

        assert extractor.key_exists(year=2023, month=3) is True


class TestEurostatExtractorRetry:
    def test_raises_extraction_error_after_retries(self, monkeypatch):
        from extractors.eurostat import EurostatExtractor, ExtractionError

        extractor = EurostatExtractor()

        with patch.object(extractor, "extract", side_effect=ConnectionError("timeout")):
            with pytest.raises(ExtractionError):
                extractor._extract_with_retry(year=2023, month=1)


class TestEurostatSchemaValidation:
    def test_valid_records_pass_validation(self):
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        records = [
            {
                "source": "eurostat",
                "dataset": "une_rt_m",
                "description": "Unemployment rate",
                "country_code": "PT",
                "year": 2023,
                "month": 3,
                "value": 6.5,
                "unit": "PC_ACT",
            }
        ]
        # Should not raise
        extractor._validate(records)

    def test_invalid_records_raise_validation_error(self):
        from extractors.base import ValidationError
        from extractors.eurostat import EurostatExtractor

        extractor = EurostatExtractor()
        records = [{"source": "wrong_source", "dataset": "une_rt_m"}]

        with pytest.raises(ValidationError):
            extractor._validate(records)
