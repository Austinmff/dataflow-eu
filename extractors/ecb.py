"""
ECB Data Portal API extractor.

Datasets extracted:
- EXR.M.USD.EUR.SP00.A  : EUR/USD monthly exchange rate
- FM.M.U2.EUR.RT0.BB.EONIA_TO.HSTA : ECB MRO (main refinancing operations) rate
- BSI.M.U2.Y.V.M10.X.1.U2.2300.Z01.E : M3 money supply (EUR area)

API docs: https://data.ecb.europa.eu/help/api/data
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import structlog

from extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)

SERIES = {
    "EXR.M.USD.EUR.SP00.A": {
        "description": "EUR/USD exchange rate (monthly average)",
        "unit": "USD",
    },
    "FM.B.U2.EUR.4F.KR.MRR_FR.LEV": {
        "description": "ECB main refinancing operations rate",
        "unit": "PERCENT",
    },
    "BSI.M.U2.Y.V.M10.X.1.U2.2300.Z01.E": {
        "description": "M3 money supply (EUR area)",
        "unit": "EUR_MILLIONS",
    },
}


class ECBExtractor(BaseExtractor):
    """
    Extracts monetary and financial indicators from the ECB Data Portal REST API.

    The ECB SDMX 2.1 API returns data in a structured JSON format with
    observations indexed by time period.
    """

    source_name = "ecb"

    schema_path = Path(__file__).parent / "schemas" / "ecb.json"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = os.environ.get(
            "ECB_BASE_URL",
            "https://data-api.ecb.europa.eu/service",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.sdmx.data+json;version=1.0.0-wd",
            }
        )

    # ------------------------------------------------------------------
    # BaseExtractor interface
    # ------------------------------------------------------------------

    def extract(self, year: int, month: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        period = f"{year}-{month:02d}"

        for series_key, meta in SERIES.items():
            log = logger.bind(series=series_key, period=period)
            log.info("fetching_series")

            raw = self._fetch_series(series_key, period)
            parsed = self._parse_response(raw, series_key, meta, year, month)
            records.extend(parsed)

            log.info("series_fetched", record_count=len(parsed))

        return records

    # ------------------------------------------------------------------
    # API interaction
    # ------------------------------------------------------------------

    def _fetch_series(self, series_key: str, period: str) -> dict[str, Any]:
        """Fetch one time series from the ECB SDMX REST API."""
        url = f"{self.base_url}/data/{series_key}"
        params = {
            "startPeriod": period,
            "endPeriod": period,
            "detail": "dataonly",
            "format": "jsondata",
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(f"ECB API timeout for {series_key}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(f"ECB API connection error for {series_key}") from exc
        except requests.exceptions.HTTPError as exc:
            if response.status_code == 404:
                # Series may not have data for this period — not an error
                logger.warning("ecb_series_no_data", series=series_key, period=period)
                return {}
            raise ExtractionError(f"ECB API HTTP {response.status_code} for {series_key}") from exc

        return response.json()

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        raw: dict[str, Any],
        series_key: str,
        meta: dict[str, Any],
        year: int,
        month: int,
    ) -> list[dict[str, Any]]:
        """
        Parse ECB SDMX JSON response into flat records.

        ECB returns observations as a dict keyed by time period string.
        Each observation is a list where index 0 is the value.
        """
        if not raw:
            return []

        records: list[dict[str, Any]] = []

        try:
            datasets = raw.get("dataSets", [])
            if not datasets:
                return []

            series_data = datasets[0].get("series", {})
            observations = next(iter(series_data.values()), {}).get("observations", {})
            time_periods = (
                raw.get("structure", {})
                .get("dimensions", {})
                .get("observation", [{}])[0]
                .get("values", [])
            )
        except (KeyError, IndexError, StopIteration) as exc:
            raise ExtractionError(f"Unexpected ECB response structure for {series_key}") from exc

        # Map time dimension index → period label
        idx_to_period = {str(i): v.get("id", "") for i, v in enumerate(time_periods)}

        for obs_idx, obs_values in observations.items():
            period_label = idx_to_period.get(obs_idx)
            value = obs_values[0] if obs_values else None

            records.append(
                {
                    "source": "ecb",
                    "series_key": series_key,
                    "description": meta["description"],
                    "period": period_label,
                    "year": year,
                    "month": month,
                    "value": value,
                    "unit": meta["unit"],
                }
            )

        return records
