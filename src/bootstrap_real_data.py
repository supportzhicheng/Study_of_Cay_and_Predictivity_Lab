"""Credentialed end-to-end acquisition and analysis bootstrap."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    connection = wrds.Connection(wrds_username=settings.wrds_username)
    LOGGER.info("Connected to WRDS and loaded accessible libraries")
    try:
        pull_wrds_data(connection, raw_dir / "wrds")
    finally:
        LOGGER.info("Closing WRDS connection")
        connection.close()


def bootstrap_real_data(settings: Settings, *, compile_report: bool = False) -> None:
    """Acquire real inputs, normalize, build, analyze, and optionally compile."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    LOGGER.setLevel(logging.INFO)
    if not settings.wrds_username:
        raise RuntimeError(
            "WRDS_USERNAME is required for the CRSP source. Set it in .env and keep "
            "the password in your PostgreSQL password file."
        )
    settings.create_directories()
    raw_dir = settings.data_dir / "raw"
    normalized_dir = settings.data_dir / "normalized"
    public_acquisition_steps = {
        "author data": partial(
            ensure_author_data, normalized_dir, vintage=settings.end_date
        ),
        "FRED data": partial(
            pull_fred_data,
            raw_dir / "fred",
            start_date=settings.start_date,
            end_date=settings.end_date,
            vintage=settings.end_date,
        ),
        "BEA data": partial(
            pull_bea_data, raw_dir / "bea", api_key=settings.bea_api_key
        ),
        "Shiller data": partial(pull_shiller_data, raw_dir / "shiller"),
    }
    with ThreadPoolExecutor(
        max_workers=len(public_acquisition_steps), thread_name_prefix="bootstrap-pull"
    ) as executor:
        futures = {
            executor.submit(_run_step, name, action): name
            for name, action in public_acquisition_steps.items()
        }
        _run_step("WRDS data", partial(_pull_wrds, settings, raw_dir))
        for future in as_completed(futures):
            future.result()

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
