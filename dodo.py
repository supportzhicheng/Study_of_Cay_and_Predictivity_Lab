"""PyDoit workflow for the core CAY replication and report."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.bootstrap_real_data import bootstrap_real_data
from src.data.build_sources import normalize_pulled_sources
from src.data.import_local import import_local_source
from src.data.pull_author_cay import ensure_author_data
from src.data.source_registry import SOURCE_REGISTRY, required_panel_sources
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import load_settings

SETTINGS = load_settings([])
PANEL_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.parquet"
PANEL_METADATA_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.metadata.json"
MANIFEST_PATH = SETTINGS.reports_dir / "build" / "artifact_manifest.json"
BOOTSTRAP_MARKER = SETTINGS.output_dir / "bootstrap_real_data.complete"
TARGETS_PATH = SETTINGS.project_root / "config" / "paper_targets.yml"

TABLE_IDS = (
    "table_ii_replication",
    "table_ii_updated",
    "table_iii_replication",
    "table_iii_updated",
    "table_vi_replication",
    "table_vi_updated",
    "table_s1_core_data_summary",
    "table_r1_replication_audit",
)
FIGURE_IDS = (
    "figure_1_replication",
    "figure_1_updated",
    "figure_s1_data_anatomy",
)
GENERATED_ARTIFACTS = (
    *(
        SETTINGS.reports_dir / "tables" / f"{artifact_id}.{suffix}"
        for artifact_id in TABLE_IDS
        for suffix in ("csv", "tex")
    ),
    *(
        SETTINGS.reports_dir / "figures" / f"{artifact_id}.{suffix}"
        for artifact_id in FIGURE_IDS
        for suffix in ("pdf", "png", "tex")
    ),
    SETTINGS.reports_dir / "paper" / "generated" / "report_metadata.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "replication_status.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "generated_captions.tex",
    SETTINGS.reports_dir / "build" / "report_metadata.json",
    SETTINGS.reports_dir / "build" / "replication_status.txt",
    SETTINGS.reports_dir / "build" / "current_vintage_cay_comparison.csv",
)
REPORT_SOURCES = (
    SETTINGS.reports_dir / "paper" / "main.tex",
    SETTINGS.reports_dir / "paper" / "preamble.tex",
    SETTINGS.reports_dir / "paper" / "references.bib",
    *sorted((SETTINGS.reports_dir / "paper" / "sections").glob("*.tex")),
)


def task_config():
    """Create ignored data and output directories."""
    return {"actions": [SETTINGS.create_directories]}


def task_pull_author_data():
    """Download and normalize pinned author validation files."""
    return {
        "actions": [
            (
                ensure_author_data,
                [SETTINGS.data_dir / "normalized"],
                {"vintage": SETTINGS.end_date},
            )
        ],
        "task_dep": ["config"],
        "targets": [
            str(SETTINGS.data_dir / "normalized" / f"{filename}.{suffix}")
            for filename in ("paper_macro_quarterly", "posted_cay_quarterly")
            for suffix in ("parquet", "metadata.json")
        ],
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
        "file_dep": [
            str(
                SETTINGS.data_dir
                / "normalized"
                / f"{SOURCE_REGISTRY[source_id].filename_stem}.parquet"
            )
            for source_id in required_panel_sources()
        ],
        "targets": [str(PANEL_PATH), str(PANEL_METADATA_PATH)],
        "task_dep": ["pull_author_data", "import_sources"],
    }


def task_generate_exhibits():
    """Generate all 32 pre-PDF report artifacts."""
    return {
        "actions": [(generate_exhibits, [SETTINGS])],
        "file_dep": [
            str(PANEL_PATH),
            str(PANEL_METADATA_PATH),
            str(TARGETS_PATH),
            str(SETTINGS.reports_dir / "captions.yml"),
            str(SETTINGS.reports_dir / "report_config.yml"),
            str(SETTINGS.reports_dir / "report_contract.yml"),
        ],
        "targets": [str(path) for path in (*GENERATED_ARTIFACTS, MANIFEST_PATH)],
        "task_dep": ["build_panel"],
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
            str(MANIFEST_PATH),
        ],
        "targets": [
            str(SETTINGS.output_dir / "01_cay_replication_tour.ipynb"),
            str(SETTINGS.output_dir / "01_cay_replication_tour.html"),
        ],
        "task_dep": ["generate_exhibits"],
    }


def task_compile_report():
    """Compile LaTeX and persist the build log."""
    return {
        "actions": [(compile_latex_report, [SETTINGS.reports_dir])],
        "file_dep": [
            str(path) for path in (*GENERATED_ARTIFACTS, MANIFEST_PATH, *REPORT_SOURCES)
        ],
        "targets": [
            str(SETTINGS.reports_dir / "build" / "main.pdf"),
            str(SETTINGS.reports_dir / "build" / "latex_build.log"),
        ],
        "task_dep": ["generate_exhibits"],
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

    def bootstrap_and_mark_complete():
        bootstrap_real_data(SETTINGS)
        BOOTSTRAP_MARKER.parent.mkdir(parents=True, exist_ok=True)
        BOOTSTRAP_MARKER.write_text(f"completed through {SETTINGS.end_date}\n")

    return {
        "actions": [bootstrap_and_mark_complete],
        "targets": [str(BOOTSTRAP_MARKER)],
    }


DOIT_CONFIG = {
    "default_tasks": [
        "generate_exhibits",
        "run_notebook",
        "compile_report",
        "run_tests",
    ]
}
