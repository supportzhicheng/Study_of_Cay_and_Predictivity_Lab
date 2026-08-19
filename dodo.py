"""PyDoit workflow for the core CAY replication and report."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.bootstrap_real_data import bootstrap_real_data
from src.data.build_sources import normalize_pulled_sources
from src.data.import_local import import_local_source
from src.data.pull_author_cay import pull_author_data
from src.data.source_registry import SOURCE_REGISTRY
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import load_settings

SETTINGS = load_settings([])
PANEL_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.parquet"


def task_config():
    """Create ignored data and output directories."""
    return {"actions": [SETTINGS.create_directories]}


def task_pull_author_data():
    """Download and normalize pinned author validation files."""
    return {
        "actions": [
            (
                pull_author_data,
                [SETTINGS.data_dir / "normalized"],
                {"vintage": SETTINGS.end_date},
            )
        ],
        "task_dep": ["config"],
    }


def task_import_sources():
    """Validate normalized local source substitutes."""

    def import_available_sources():
        for source_id, spec in SOURCE_REGISTRY.items():
            candidates = list(SETTINGS.p10_input_dir.glob(f"{spec.filename_stem}.*"))
            if candidates:
                import_local_source(
                    source_id,
                    SETTINGS.p10_input_dir,
                    SETTINGS.data_dir / "normalized",
                    vintage=SETTINGS.end_date,
                )

    return {"actions": [import_available_sources], "task_dep": ["config"]}


def task_normalize_pulled_sources():
    """Transform standard live-pull caches into quarterly contracts."""
    return {
        "actions": [
            (
                normalize_pulled_sources,
                [SETTINGS.data_dir / "raw", SETTINGS.data_dir / "normalized"],
                {"vintage": SETTINGS.end_date},
            )
        ],
        "task_dep": ["config"],
    }


def task_build_panel():
    """Merge normalized sources and write panel metadata."""
    return {
        "actions": [(build_panel, [SETTINGS])],
        "targets": [str(PANEL_PATH)],
        "task_dep": ["config"],
    }


def task_generate_exhibits():
    """Generate all 32 pre-PDF report artifacts."""
    return {
        "actions": [(generate_exhibits, [SETTINGS])],
        "file_dep": [str(PANEL_PATH)],
        "targets": [str(SETTINGS.reports_dir / "build" / "artifact_manifest.json")],
    }


def _run_notebook() -> None:
    output_dir = SETTINGS.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    source = SETTINGS.project_root / "notebooks" / "01_cay_replication_tour.ipynb"
    subprocess.run(
        [
            str(Path(__import__("sys").executable)),
            "-m",
            "jupyter",
            "nbconvert",
            "--execute",
            "--to=notebook",
            f"--output-dir={output_dir}",
            str(source),
        ],
        check=True,
    )
    executed = output_dir / source.name
    subprocess.run(
        [
            str(Path(__import__("sys").executable)),
            "-m",
            "jupyter",
            "nbconvert",
            "--to=html",
            f"--output-dir={output_dir}",
            str(executed),
        ],
        check=True,
    )


def task_run_notebook():
    """Execute the inspection notebook and export HTML."""
    return {
        "actions": [_run_notebook],
        "file_dep": [
            str(PANEL_PATH),
            str(SETTINGS.reports_dir / "build" / "artifact_manifest.json"),
        ],
        "targets": [
            str(SETTINGS.output_dir / "01_cay_replication_tour.ipynb"),
            str(SETTINGS.output_dir / "01_cay_replication_tour.html"),
        ],
    }


def task_compile_report():
    """Compile LaTeX and persist the build log."""
    return {
        "actions": [(compile_latex_report, [SETTINGS.reports_dir])],
        "file_dep": [str(SETTINGS.reports_dir / "build" / "artifact_manifest.json")],
        "targets": [str(SETTINGS.reports_dir / "build" / "main.pdf")],
    }


def task_run_tests():
    """Run deterministic tests and write JUnit XML."""
    SETTINGS.output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "actions": [
            f"{__import__('sys').executable} -m pytest -q "
            f"--junitxml={SETTINGS.output_dir / 'pytest.xml'}"
        ],
        "targets": [str(SETTINGS.output_dir / "pytest.xml")],
    }


def task_bootstrap_real_data():
    """Run credentialed acquisition and complete analysis."""
    return {
        "actions": [(bootstrap_real_data, [SETTINGS])],
        "targets": [str(SETTINGS.reports_dir / "build" / "artifact_manifest.json")],
    }


DOIT_CONFIG = {
    "default_tasks": [
        "bootstrap_real_data",
        "run_notebook",
        "compile_report",
        "run_tests",
    ]
}
