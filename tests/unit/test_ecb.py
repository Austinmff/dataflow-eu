"""
Unit tests for ECBExtractor.

Uses moto to mock S3 — no real AWS or LocalStack required.
HTTP responses from the ECB API are mocked via unittest.mock.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_ECB_RESPONSE = {
    "dataSets": [
        {
            "series": {
                "0:0:0:0:0": {
                    "observations": {
                        "0": [1.0823, 0],
                        "1": [1.0756, 0],
                    }
                }
            }
        }
    ],
    "structure": {
        "dimensions": {
            "observation": [
                {
                    "id": "TIME_PERIOD",
                    "values": [
                        {"id": "2023-01", "name": "2023-01"},
                        {"id": "2023-02", "name": "2023-02"},
                    ],
                }
            ]
        }
    },
}


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("S3_BUCKET_NAME", "test-bronze-bucket")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
    monkeypatch.setenv("AWS_ENDPOINT_URL", "")
    monkeypatch.setenv("ECB_BASE_URL", "https://fake-ecb.eu/service")


@pytest.fixture
def s3_bucket():
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


class TestECBExtractorParsing:
    def test_parse_response_returns_flat_records(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        meta = {"description": "EUR/USD exchange rate", "unit": "USD"}
        records = extractor._parse_response(
            FAKE_ECB_RESPONSE,
            "EXR.M.USD.EUR.SP00.A",
            meta,
            year=2023,
            month=1,
        )

        assert len(records) == 2
        assert records[0]["value"] == 1.0823
        assert records[0]["series_key"] == "EXR.M.USD.EUR.SP00.A"
        assert records[0]["source"] == "ecb"

    def test_parse_response_empty_datasets(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        meta = {"description": "EUR/USD exchange rate", "unit": "USD"}
        records = extractor._parse_response({}, "EXR.M.USD.EUR.SP00.A", meta, 2023, 1)
        assert records == []

    def test_parse_response_no_observations(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        meta = {"description": "EUR/USD exchange rate", "unit": "USD"}
        empty = {**FAKE_ECB_RESPONSE, "dataSets": [{"series": {"0:0:0:0:0": {"observations": {}}}}]}
        records = extractor._parse_response(empty, "EXR.M.USD.EUR.SP00.A", meta, 2023, 1)
        assert records == []


class TestECBExtractorS3:
    def test_s3_key_format(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        key = extractor._s3_key(year=2023, month=1)
        assert key == "ecb/year=2023/month=01/data.json"

    def test_upload_writes_correct_payload(self, s3_bucket):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        extractor._s3_client = s3_bucket

        records = [
            {
                "source": "ecb",
                "series_key": "EXR.M.USD.EUR.SP00.A",
                "description": "EUR/USD exchange rate",
                "period": "2023-01",
                "year": 2023,
                "month": 1,
                "value": 1.0823,
                "unit": "USD",
            }
        ]
        key = extractor._upload(records, year=2023, month=1)

        obj = s3_bucket.get_object(Bucket="test-bronze-bucket", Key=key)
        body = json.loads(obj["Body"].read())

        assert body["source"] == "ecb"
        assert body["record_count"] == 1
        assert body["records"][0]["value"] == 1.0823


class TestECBExtractorHTTP:
    def test_404_returns_empty_records(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()

        mock_response = MagicMock()
        mock_response.status_code = 404

        import requests

        http_error = requests.exceptions.HTTPError(response=mock_response)

        with patch.object(extractor.session, "get", side_effect=http_error):
            result = extractor._fetch_series("NONEXISTENT.SERIES", "2023-01")
            assert result == {}

    def test_timeout_raises_timeout_error(self):
        import requests

        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()

        with patch.object(
            extractor.session,
            "get",
            side_effect=requests.exceptions.Timeout,
        ):
            with pytest.raises(TimeoutError):
                extractor._fetch_series("EXR.M.USD.EUR.SP00.A", "2023-01")

    def test_connection_error_raises_connection_error(self):
        import requests

        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()

        with patch.object(
            extractor.session,
            "get",
            side_effect=requests.exceptions.ConnectionError,
        ):
            with pytest.raises(ConnectionError):
                extractor._fetch_series("EXR.M.USD.EUR.SP00.A", "2023-01")

    def test_non_404_http_error_raises_extraction_error(self):
        import requests

        from extractors.base import ExtractionError
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()

        mock_response = MagicMock()
        mock_response.status_code = 500
        http_error = requests.exceptions.HTTPError(response=mock_response)

        with patch.object(extractor.session, "get", side_effect=http_error):
            with pytest.raises(ExtractionError):
                extractor._fetch_series("EXR.M.USD.EUR.SP00.A", "2023-01")


class TestECBExtractorEndToEnd:
    def test_extract_calls_fetch_and_parse_for_every_series(self):
        from extractors.ecb import SERIES, ECBExtractor

        extractor = ECBExtractor()

        with patch.object(extractor, "_fetch_series", return_value=FAKE_ECB_RESPONSE) as mock_fetch:
            records = extractor.extract(year=2023, month=1)

        assert mock_fetch.call_count == len(SERIES)
        # Each series in FAKE_ECB_RESPONSE produces 2 records
        assert len(records) == 2 * len(SERIES)

    def test_extract_handles_empty_series_gracefully(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()

        with patch.object(extractor, "_fetch_series", return_value={}):
            records = extractor.extract(year=2023, month=1)

        assert records == []


class TestECBSchemaValidation:
    def test_valid_records_pass_validation(self):
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        records = [
            {
                "source": "ecb",
                "series_key": "EXR.M.USD.EUR.SP00.A",
                "description": "EUR/USD",
                "period": "2023-01",
                "year": 2023,
                "month": 1,
                "value": 1.0823,
                "unit": "USD",
            }
        ]
        extractor._validate(records)

    def test_missing_required_field_raises(self):
        from extractors.base import ValidationError
        from extractors.ecb import ECBExtractor

        extractor = ECBExtractor()
        records = [{"source": "ecb"}]  # missing series_key, year, month

        with pytest.raises(ValidationError):
            extractor._validate(records)
