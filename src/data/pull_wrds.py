"""Acquire licensed monthly CRSP market and Treasury inputs from WRDS."""

from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Any, Protocol, Sequence

import pandas as pd

from src.settings import load_settings

LOGGER = logging.getLogger(__name__)

MARKET_TABLE_CANDIDATES = ("crsp.msi", "crspm.msi")
TREASURY_TABLE_CANDIDATES = ("crspm.mcti", "crsp.mcti")
MARKET_FIELDS = ("date", "vwretd", "vwretx")
TREASURY_FIELDS = ("caldt", "t30ret", "t90ret")
SAFE_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


class WrdsConnection(Protocol):
    def list_tables(self, library: str) -> list[str]: ...

    def raw_sql(self, sql: str, **kwargs: Any) -> pd.DataFrame: ...


def validate_table_name(table_name: str) -> str:
    """Allow only schema-qualified lowercase SQL identifiers."""
    if not SAFE_TABLE_NAME.fullmatch(table_name):
        raise ValueError(f"Unsafe WRDS table name: {table_name!r}")
    return table_name


def discover_table(connection: WrdsConnection, candidates: tuple[str, ...]) -> str:
    """Return the first available table in the declared tie-break order."""
    available_by_library: dict[str, set[str]] = {}
    for candidate in candidates:
        validate_table_name(candidate)
        library, table = candidate.split(".", 1)
        if library not in available_by_library:
            available_by_library[library] = set(connection.list_tables(library))
        if table in available_by_library[library]:
            return candidate
    raise RuntimeError(
        f"None of the WRDS tables are available: {', '.join(candidates)}"
    )


def build_select_query(table_name: str, fields: tuple[str, ...]) -> str:
    """Build a query from predeclared fields and a validated table name."""
    table = validate_table_name(table_name)
    if not fields or any(
        not re.fullmatch(r"[a-z][a-z0-9_]*", field) for field in fields
    ):
        raise ValueError("Unsafe or empty WRDS field list.")
    return f"SELECT {', '.join(fields)} FROM {table}"


def pull_wrds_data(connection: WrdsConnection, raw_dir: Path) -> tuple[Path, Path]:
    """Discover subscription tables and write raw monthly CRSP caches."""
    LOGGER.info("Discovering subscribed WRDS market table")
    market_table = discover_table(connection, MARKET_TABLE_CANDIDATES)
    LOGGER.info("Using WRDS market table %s", market_table)
    LOGGER.info("Discovering subscribed WRDS Treasury table")
    treasury_table = discover_table(connection, TREASURY_TABLE_CANDIDATES)
    LOGGER.info("Using WRDS Treasury table %s", treasury_table)
    LOGGER.info("Downloading WRDS market history")
    market = connection.raw_sql(
        build_select_query(market_table, MARKET_FIELDS), date_cols=["date"]
    )
    LOGGER.info("Downloaded %d WRDS market rows", len(market))
    LOGGER.info("Downloading WRDS Treasury history")
    treasury = connection.raw_sql(
        build_select_query(treasury_table, TREASURY_FIELDS), date_cols=["caldt"]
    )
    LOGGER.info("Downloaded %d WRDS Treasury rows", len(treasury))
    raw_dir.mkdir(parents=True, exist_ok=True)
    market_path = raw_dir / "crsp_market_monthly.parquet"
    treasury_path = raw_dir / "crsp_treasury_monthly.parquet"
    market.to_parquet(market_path, index=False)
    treasury.to_parquet(treasury_path, index=False)
    LOGGER.info("Wrote WRDS raw caches to %s", raw_dir)
    return market_path, treasury_path


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args(argv)
    settings = load_settings(argv=[])
    if not settings.wrds_username:
        raise RuntimeError(
            "WRDS_USERNAME is not configured. Set it in .env and keep the password "
            "in your PostgreSQL password file."
        )

    import wrds

    connection = wrds.Connection(wrds_username=settings.wrds_username)
    try:
        paths = pull_wrds_data(
            connection, args.raw_dir or settings.data_dir / "raw" / "wrds"
        )
    finally:
        connection.close()
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
