"""
Eurostat REST API extractor.

Datasets extracted:
- nama_10_pc  : GDP per capita (current prices, EUR)
- une_rt_m    : Unemployment rate (monthly, seasonally adjusted)
- prc_hicp_manr: HICP inflation rate (monthly, annual rate of change)
- demo_pjan   : Population on 1 January

API docs: https://ec.europa.eu/eurostat/web/json-and-unicode-web-services
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests
import structlog

from extractors.base import BaseExtractor, ExtractionError

logger = structlog.get_logger(__name__)

# EU-27 + candidate countries of interest
TARGET_COUNTRIES = [
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "EL", "ES",
    "FI", "FR", "HR", "HU", "IE", "IT", "LT", "LU", "LV", "MT",
    "NL", "PL", "PT", "RO", "SE", "SI", "SK", "EU27_2020",
]

DATASETS = {
    "nama_10_pc": {
        "description": "GDP per capita",
        "unit": "CP_EUR_HAB",  # current prices, EUR per inhabitant
        "na_item": "B1GQ",
    },
    "une_rt_m": {
        "description": "Unemployment rate",
        "unit": "PC_ACT",    # percentage of active population
        "sex": "T",           # total
        "age": "TOTAL",
    },
    "prc_hicp_manr": {
        "description": "HICP inflation rate",
        "unit": "RCH_A",     # annual rate of change
        "coicop": "CP00",    # all items
    },
    "demo_pjan": {
        "description": "Population on 1 January",
        "unit": "NR",
        "sex": "T",
        "age": "TOTAL",
    },
}


class EurostatExtractor(BaseExtractor):
    """
    Extracts economic indicators from the Eurostat JSON API.

    One call per dataset per (year, month) partition.
    Monthly datasets (une_rt_m, prc_hicp_manr) use the exact month.
    Annual datasets (nama_10_pc, demo_pjan) use month=1 as convention.
    """

    source_name = "eurostat"

    schema_path = Path(__file__).parent / "schemas" / "eurostat.json"

    def __init__(self) -> None:
        super().__init__()
        self.base_url = os.environ.get(
            "EUROSTAT_BASE_URL",
            "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0",
        )
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    # ------------------------------------------------------------------
    # BaseExtractor interface
    # ------------------------------------------------------------------

    def extract(self, year: int, month: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        for dataset_code, meta in DATASETS.items():
            log = logger.bind(dataset=dataset_code, year=year, month=month)

            # Annual datasets: only run for January
            if dataset_code in ("nama_10_pc", "demo_pjan") and month != 1:
                log.debug("skipping_annual_dataset_non_january_month")
                continue

            log.info("fetching_dataset")
            raw = self._fetch_dataset(dataset_code, year, month)
            parsed = self._parse_response(raw, dataset_code, meta, year, month)
            records.extend(parsed)
            log.info("dataset_fetched", record_count=len(parsed))

        return records

    # ------------------------------------------------------------------
    # API interaction
    # ------------------------------------------------------------------

    def _fetch_dataset(self, dataset: str, year: int, month: int) -> dict[str, Any]:
        """Call the Eurostat JSON API and return the raw response dict."""
        period = f"{year}-{month:02d}" if month else str(year)

        url = f"{self.base_url}/data/{dataset}"
        params: dict[str, Any] = {
            "format": "JSON",
            "lang": "EN",
            "geo": TARGET_COUNTRIES,
            "time": period,
        }

        # Dataset-specific filters
        meta = DATASETS[dataset]
        if "unit" in meta:
            params["unit"] = meta["unit"]
        if "na_item" in meta:
            params["na_item"] = meta["na_item"]
        if "sex" in meta:
            params["sex"] = meta["sex"]
        if "age" in meta:
            params["age"] = meta["age"]
        if "coicop" in meta:
            params["coicop"] = meta["coicop"]

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(f"Eurostat API timeout for {dataset}") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(f"Eurostat API connection error for {dataset}") from exc
        except requests.exceptions.HTTPError as exc:
            raise ExtractionError(
                f"Eurostat API HTTP {response.status_code} for {dataset}: {response.text[:200]}"
            ) from exc

        return response.json()

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        raw: dict[str, Any],
        dataset_code: str,
        meta: dict[str, Any],
        year: int,
        month: int,
    ) -> list[dict[str, Any]]:
        """
        Transform the Eurostat JSON-stat response into flat records.

        Eurostat returns data in JSON-stat format where values are indexed
        by a flat integer index mapped through dimension arrays.
        """
        records: list[dict[str, Any]] = []

        try:
            value_map: dict[str, float | None] = raw.get("value", {})
            dimensions = raw.get("dimension", {})
            geo_index: dict[str, int] = dimensions.get("geo", {}).get("category", {}).get("index", {})
        except (KeyError, AttributeError) as exc:
            raise ExtractionError(
                f"Unexpected Eurostat response structure for {dataset_code}"
            ) from exc

        # Invert the geo index so we can look up country by position
        idx_to_geo = {v: k for k, v in geo_index.items()}

        for idx_str, value in value_map.items():
            idx = int(idx_str)
            country_code = idx_to_geo.get(idx)
            if country_code is None:
                continue

            records.append({
                "source": "eurostat",
                "dataset": dataset_code,
                "description": meta["description"],
                "country_code": country_code,
                "year": year,
                "month": month,
                "value": value,
                "unit": meta.get("unit"),
            })

        return records
