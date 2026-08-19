"""Credentialed end-to-end acquisition and analysis bootstrap."""

from __future__ import annotations

import argparse
from typing import Sequence

from src.data.build_sources import normalize_pulled_sources
from src.data.pull_author_cay import ensure_author_data
from src.data.pull_bea import pull_bea_data
from src.data.pull_fred import pull_fred_data
from src.data.pull_shiller import pull_shiller_data
from src.data.pull_wrds import pull_wrds_data
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import Settings, load_settings


def bootstrap_real_data(settings: Settings, *, compile_report: bool = False) -> None:
    """Acquire real inputs, normalize, build, analyze, and optionally compile."""
    if not settings.wrds_username:
        raise RuntimeError(
            "WRDS_USERNAME is required for the CRSP source. Set it in .env and keep "
            "the password in your PostgreSQL password file."
        )
    settings.create_directories()
    raw_dir = settings.data_dir / "raw"
    normalized_dir = settings.data_dir / "normalized"
    ensure_author_data(normalized_dir, vintage=settings.end_date)
    pull_fred_data(
        raw_dir / "fred",
        start_date=settings.start_date,
        end_date=settings.end_date,
        vintage=settings.end_date,
    )
    pull_bea_data(raw_dir / "bea", api_key=settings.bea_api_key)
    pull_shiller_data(raw_dir / "shiller")

    import wrds

    connection = wrds.Connection(wrds_username=settings.wrds_username)
    try:
        pull_wrds_data(connection, raw_dir / "wrds")
    finally:
        connection.close()
    normalize_pulled_sources(raw_dir, normalized_dir, vintage=settings.end_date)
    build_panel(settings)
    generate_exhibits(settings)
    if compile_report:
        compile_latex_report(settings.reports_dir)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-report", action="store_true")
    args, setting_args = parser.parse_known_args(argv)
    bootstrap_real_data(load_settings(setting_args), compile_report=args.compile_report)


if __name__ == "__main__":
    main()
