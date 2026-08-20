"""Credentialed end-to-end acquisition and analysis bootstrap."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from functools import partial
from pathlib import Path
from time import monotonic
from typing import Any, Sequence

from src.data.build_sources import normalize_pulled_sources
from src.data.pull_author_cay import ensure_author_data
from src.data.pull_bea import pull_bea_data
from src.data.pull_fred import pull_fred_data
from src.data.pull_shiller import pull_shiller_data
from src.data.pull_wrds import pull_wrds_data
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import Settings, load_settings

LOGGER = logging.getLogger(__name__)
CORE_RAW_FILES = (
    Path("fred/fred_inputs.parquet"),
    Path("bea/bea_components.parquet"),
    Path("shiller/shiller_monthly.parquet"),
    Path("wrds/crsp_market_monthly.parquet"),
    Path("wrds/crsp_treasury_monthly.parquet"),
)


def _run_step(name: str, action: Callable[[], Any]) -> Any:
    """Run one bootstrap step with visible timing and failure context."""
    started_at = monotonic()
    LOGGER.info("Starting %s", name)
    try:
        result = action()
    except Exception:
        LOGGER.exception("Failed %s after %.1f seconds", name, monotonic() - started_at)
        raise
    LOGGER.info("Completed %s in %.1f seconds", name, monotonic() - started_at)
    return result


def _pull_wrds(settings: Settings, raw_dir: Path) -> None:
    """Open a short-lived WRDS connection and acquire CRSP inputs."""
    import wrds

    LOGGER.info("Connecting to WRDS")
    connection = wrds.Connection(
        wrds_username=settings.wrds_username,
        wrds_password=settings.wrds_password or "",
    )
    LOGGER.info("Connected to WRDS and loaded accessible libraries")
    try:
        pull_wrds_data(connection, raw_dir / "wrds")
    finally:
        LOGGER.info("Closing WRDS connection")
        connection.close()


def acquire_core_data(settings: Settings) -> list[Path]:
    """Acquire missing live core raw caches and return all required paths."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    LOGGER.setLevel(logging.INFO)
    settings.create_directories()
    raw_dir = settings.data_dir / "raw"
    fred_raw = raw_dir / "fred" / "fred_inputs.parquet"
    bea_raw = raw_dir / "bea" / "bea_components.parquet"
    shiller_raw = raw_dir / "shiller" / "shiller_monthly.parquet"
    wrds_market_raw = raw_dir / "wrds" / "crsp_market_monthly.parquet"
    wrds_treasury_raw = raw_dir / "wrds" / "crsp_treasury_monthly.parquet"

    if not fred_raw.exists():
        _run_step(
            "FRED data",
            partial(
                pull_fred_data,
                raw_dir / "fred",
                start_date=settings.start_date,
                end_date=settings.end_date,
                vintage=settings.end_date,
            ),
        )
    if not bea_raw.exists():
        _run_step(
            "BEA data",
            partial(pull_bea_data, raw_dir / "bea", api_key=settings.bea_api_key),
        )
    if not shiller_raw.exists():
        _run_step("Shiller data", partial(pull_shiller_data, raw_dir / "shiller"))
    if not (wrds_market_raw.exists() and wrds_treasury_raw.exists()):
        if not settings.wrds_username:
            raise RuntimeError(
                "WRDS_USERNAME is required for missing CRSP caches. Set it in .env "
                "and keep the password in your PostgreSQL password file."
            )
        _run_step("WRDS data", partial(_pull_wrds, settings, raw_dir))
    return [raw_dir / relative for relative in CORE_RAW_FILES]


def bootstrap_real_data(settings: Settings, *, compile_report: bool = False) -> None:
    """Acquire real inputs, normalize, build, analyze, and optionally compile."""
    acquire_core_data(settings)
    raw_dir = settings.data_dir / "raw"
    normalized_dir = settings.data_dir / "normalized"
    _run_step(
        "author data",
        partial(ensure_author_data, normalized_dir, vintage=settings.end_date),
    )

    _run_step(
        "source normalization",
        partial(
            normalize_pulled_sources,
            raw_dir,
            normalized_dir,
            vintage=settings.end_date,
        ),
    )
    _run_step("panel build", partial(build_panel, settings))
    _run_step("exhibit generation", partial(generate_exhibits, settings))
    if compile_report:
        _run_step(
            "LaTeX report compilation",
            partial(compile_latex_report, settings.reports_dir),
        )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-report", action="store_true")
    args, setting_args = parser.parse_known_args(argv)
    bootstrap_real_data(load_settings(setting_args), compile_report=args.compile_report)


if __name__ == "__main__":
    main()
