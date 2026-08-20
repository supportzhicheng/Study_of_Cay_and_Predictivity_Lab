"""Acquire pinned BEA NIPA components through an injectable HTTP boundary."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import pandas as pd
import requests

from src.settings import load_settings

BEA_API_URL = "https://apps.bea.gov/api/data"


@dataclass(frozen=True)
class BeaComponent:
    name: str
    dataset: str
    table: str
    line_description: str
    prefix_match: bool = False


BEA_COMPONENTS = (
    BeaComponent("nondurable_goods", "NIPA", "T20305", "Nondurable goods"),
    BeaComponent("services", "NIPA", "T20305", "Services"),
    BeaComponent(
        "clothing_footwear",
        "NIPA",
        "T20305",
        "Clothing and footwear",
    ),
    BeaComponent("wages", "NIPA", "T20100", "Wages and salaries"),
    BeaComponent("transfers", "NIPA", "T20100", "Personal current transfer receipts"),
    BeaComponent("supplements", "NIPA", "T20100", "Supplements to wages and salaries"),
    BeaComponent(
        "social_insurance",
        "NIPA",
        "T20100",
        "Less: Contributions for government social insurance, domestic",
    ),
    BeaComponent("personal_taxes", "NIPA", "T20100", "Less: Personal current taxes"),
    BeaComponent(
        "proprietors_income",
        "NIPA",
        "T20100",
        "Proprietors' income with inventory valuation and capital consumption adjustments",
    ),
    BeaComponent(
        "rental_income",
        "NIPA",
        "T20100",
        "Rental income of persons with capital consumption adjustment",
    ),
    BeaComponent("dividend_income", "NIPA", "T20100", "Personal dividend income"),
    BeaComponent("interest_income", "NIPA", "T20100", "Personal interest income"),
)


class HttpResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> dict[str, Any]: ...


class HttpSession(Protocol):
    def get(
        self, url: str, *, params: dict[str, str], timeout: int
    ) -> HttpResponse: ...


def build_bea_params(component: BeaComponent, api_key: str | None) -> dict[str, str]:
    """Build the pinned quarterly BEA request for one table."""
    return {
        "UserID": api_key or "sample-key",
        "method": "GetData",
        "datasetname": component.dataset,
        "TableName": component.table,
        "Frequency": "Q",
        "Year": "X",
        "ResultFormat": "JSON",
    }


def _bea_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        rows = payload["BEAAPI"]["Results"]["Data"]
    except (KeyError, TypeError) as exc:
        raise ValueError("BEA response does not contain Results.Data.") from exc
    if not isinstance(rows, list):
        raise ValueError("BEA Results.Data must be a list.")
    return rows


def select_component_rows(
    rows: list[dict[str, Any]], component: BeaComponent
) -> pd.Series:
    """Resolve exactly one BEA line description and return quarterly values."""
    descriptions = {str(row.get("LineDescription", "")).strip() for row in rows}
    if component.prefix_match:
        matches = sorted(
            value
            for value in descriptions
            if value.startswith(component.line_description)
        )
    else:
        matches = (
            [component.line_description]
            if component.line_description in descriptions
            else []
        )
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one BEA line for '{component.name}', found {len(matches)}."
        )

    selected = [
        row for row in rows if str(row.get("LineDescription", "")).strip() == matches[0]
    ]
    quarters = pd.PeriodIndex([row["TimePeriod"] for row in selected], freq="Q")
    values = pd.to_numeric(
        pd.Series([str(row["DataValue"]).replace(",", "") for row in selected]),
        errors="raise",
    )
    return pd.Series(
        values.to_numpy(), index=quarters, name=component.name
    ).sort_index()


def fetch_bea_component(
    component: BeaComponent,
    *,
    api_key: str | None,
    session: HttpSession | None = None,
) -> pd.Series:
    """Fetch and resolve one BEA component."""
    client = session or requests.Session()
    response = client.get(
        BEA_API_URL,
        params=build_bea_params(component, api_key),
        timeout=60,
    )
    response.raise_for_status()
    return select_component_rows(_bea_rows(response.json()), component)


def pull_bea_data(
    raw_dir: Path,
    *,
    api_key: str | None,
    session: HttpSession | None = None,
) -> Path:
    """Fetch all pinned BEA components and write an aligned raw cache."""
    series = [
        fetch_bea_component(component, api_key=api_key, session=session)
        for component in BEA_COMPONENTS
    ]
    frame = pd.concat(series, axis=1).sort_index()
    frame.index.name = "quarter"
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / "bea_components.parquet"
    frame.to_parquet(path)
    manifest = raw_dir / "bea_components.requests.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "name": component.name,
                    "dataset": component.dataset,
                    "table": component.table,
                    "line_description": component.line_description,
                }
                for component in BEA_COMPONENTS
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    print(
        pull_bea_data(
            args.raw_dir or settings.data_dir / "raw" / "bea",
            api_key=settings.bea_api_key,
        )
    )


if __name__ == "__main__":
    main()
