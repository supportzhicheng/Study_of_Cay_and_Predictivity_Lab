"""Command dispatch for panel, exhibits, full analysis, and report compilation."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.data.build_quarterly_panel import build_quarterly_panel, write_quarterly_panel
from src.data.source_registry import SOURCE_REGISTRY, required_panel_sources
from src.reporting.generate import generate_report_artifacts
from src.reporting.latex import compile_latex_report
from src.settings import Settings, load_settings


def _git_commit(project_root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "UNKNOWN"


def load_normalized_sources(
    normalized_dir: Path,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Load all required normalized caches plus optional posted validation CAY."""
    sources: dict[str, pd.DataFrame] = {}
    vintages: dict[str, str] = {}
    source_ids = list(required_panel_sources()) + ["posted_cay"]
    for source_id in source_ids:
        spec = SOURCE_REGISTRY[source_id]
        data_path = normalized_dir / f"{spec.filename_stem}.parquet"
        metadata_path = normalized_dir / f"{spec.filename_stem}.metadata.json"
        if not data_path.exists():
            if spec.required_for_panel:
                raise FileNotFoundError(
                    f"Missing normalized source '{source_id}': {data_path}. "
                    "Run source acquisition/import and python -m src.data.build_sources."
                )
            continue
        sources[source_id] = pd.read_parquet(data_path)
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            vintages[source_id] = str(metadata.get("vintage", "UNKNOWN"))
    return sources, vintages


def build_panel(settings: Settings) -> Path:
    """Load normalized sources and write the processed quarterly panel."""
    sources, vintages = load_normalized_sources(settings.data_dir / "normalized")
    panel = build_quarterly_panel(sources)
    data_path, _ = write_quarterly_panel(
        panel, settings.data_dir / "processed", source_vintages=vintages
    )
    return data_path


def generate_exhibits(settings: Settings) -> list[Path]:
    """Generate all report artifacts from the processed panel."""
    panel_path = settings.data_dir / "processed" / "core_quarterly.parquet"
    if not panel_path.exists():
        raise FileNotFoundError(
            f"Processed panel is missing: {panel_path}. Run panel first."
        )
    panel = pd.read_parquet(panel_path)
    if not isinstance(panel.index, pd.PeriodIndex):
        panel.index = pd.PeriodIndex(panel.index, freq="Q")
    return generate_report_artifacts(
        panel,
        settings.reports_dir,
        settings.project_root / "config" / "paper_targets.yml",
        panel_path=panel_path,
        panel_metadata_path=(
            settings.data_dir / "processed" / "core_quarterly.metadata.json"
        ),
        data_vintage=settings.end_date,
        git_commit=_git_commit(settings.project_root),
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("panel", "exhibits", "all", "report"))
    args, setting_args = parser.parse_known_args(argv)
    settings = load_settings(setting_args)
    if args.command in {"panel", "all"}:
        print(build_panel(settings))
    if args.command in {"exhibits", "all"}:
        for path in generate_exhibits(settings):
            print(path)
    if args.command == "report":
        print(compile_latex_report(settings.reports_dir))


if __name__ == "__main__":
    main()
