"""PyDoit workflow for the core CAY replication and report."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from shutil import copy2

from cay_lab.dodo import build_chartbook
from cay_lab.pipeline import (
    PANEL_STEM as EXTENSION_PANEL_STEM,
)
from cay_lab.pipeline import (
    REGION_NORMALIZED_STEM,
    build_extension_panel,
    generate_combined_report,
    generate_extension_exhibits,
    import_region_data,
)
from cay_lab.settings import load_extension_settings
from src.bootstrap_real_data import bootstrap_real_data
from src.data.build_sources import normalize_pulled_sources
from src.data.import_local import import_local_source
from src.data.pull_author_cay import ensure_author_data
from src.data.source_registry import SOURCE_REGISTRY, required_panel_sources
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import load_settings

SETTINGS = load_settings([])
EXTENSION_SETTINGS = load_extension_settings()
PANEL_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.parquet"
PANEL_METADATA_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.metadata.json"
MANIFEST_PATH = SETTINGS.reports_dir / "build" / "artifact_manifest.json"
BOOTSTRAP_MARKER = SETTINGS.output_dir / "bootstrap_real_data.complete"
TARGETS_PATH = SETTINGS.project_root / "config" / "paper_targets.yml"
EXTENSION_REGION_SOURCE_CSV = (
    EXTENSION_SETTINGS.cay_data_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
)
EXTENSION_REGION_NORMALIZED_PARQUET = (
    EXTENSION_SETTINGS.output_dir / f"{REGION_NORMALIZED_STEM}.parquet"
)
EXTENSION_REGION_NORMALIZED_META = (
    EXTENSION_SETTINGS.output_dir / f"{REGION_NORMALIZED_STEM}.metadata.json"
)
EXTENSION_PANEL_PARQUET = (
    EXTENSION_SETTINGS.output_dir / f"{EXTENSION_PANEL_STEM}.parquet"
)
EXTENSION_PANEL_META = (
    EXTENSION_SETTINGS.output_dir / f"{EXTENSION_PANEL_STEM}.metadata.json"
)
EXTENSION_REPORT_TEX = (
    EXTENSION_SETTINGS.reports_dir / "combined_replication_extension.tex"
)
EXTENSION_EXHIBIT_ARTIFACTS = (
    EXTENSION_SETTINGS.output_dir / "extension_prepared.csv",
    EXTENSION_SETTINGS.output_dir / "extension_rolling.csv",
    EXTENSION_SETTINGS.output_dir / "extension_chartbook.pdf",
    EXTENSION_SETTINGS.output_dir / "extension_qa.json",
)
SECTION9_CHARTBOOK_OUTPUT_DIR = (
    EXTENSION_SETTINGS.project_root
    / "cay_lab"
    / "output"
    / "examples"
    / "wealth_groups_2023Q1_2026Q1_h2_QQQ_train8"
)
SECTION9_CHARTBOOK_TARGETS = (
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_prepared.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_tests.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_rolling.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "chartbook_subcay_predictivity.pdf",
)

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


def _run_tests_action() -> None:
    subprocess.run(
        [
            str(Path(sys.executable)),
            "-m",
            "pytest",
            "-q",
            f"--junitxml={SETTINGS.output_dir / 'pytest.xml'}",
        ],
        check=True,
    )


def task_config():
    """Create ignored data and output directories."""
    return {"actions": [SETTINGS.create_directories]}


def task_pull_author_data():
    """Download and normalize pinned author validation files."""

    def pull_author_data():
        ensure_author_data(SETTINGS.data_dir / "normalized", vintage=SETTINGS.end_date)

    return {
        "actions": [pull_author_data],
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

    def normalize_sources():
        normalize_pulled_sources(
            SETTINGS.data_dir / "raw",
            SETTINGS.data_dir / "normalized",
            vintage=SETTINGS.end_date,
        )

    return {
        "actions": [normalize_sources],
        "task_dep": ["config"],
    }


def task_build_panel():
    """Merge normalized sources and write panel metadata."""

    def build():
        build_panel(SETTINGS)

    return {
        "actions": [build],
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

    def generate():
        generate_exhibits(SETTINGS)

    return {
        "actions": [generate],
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
    kernel_name = f"cay-runtime-py{sys.version_info.major}{sys.version_info.minor}"
    subprocess.run(
        [
            str(Path(sys.executable)),
            "-m",
            "ipykernel",
            "install",
            "--user",
            "--name",
            kernel_name,
            "--display-name",
            kernel_name,
        ],
        check=True,
    )
    output_dir = SETTINGS.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    source = SETTINGS.project_root / "notebooks" / "01_cay_replication_tour.ipynb"
    subprocess.run(
        [
            str(Path(sys.executable)),
            "-m",
            "jupyter",
            "nbconvert",
            "--execute",
            f"--ExecutePreprocessor.kernel_name={kernel_name}",
            "--to=notebook",
            f"--output-dir={output_dir}",
            str(source),
        ],
        check=True,
    )
    executed = output_dir / source.name
    subprocess.run(
        [
            str(Path(sys.executable)),
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

    def compile_report():
        main_pdf = compile_latex_report(SETTINGS.reports_dir)
        test_pdf = SETTINGS.reports_dir / "build" / "test_main.pdf"
        copy2(main_pdf, test_pdf)

    return {
        "actions": [compile_report],
        "file_dep": [
            str(path) for path in (*GENERATED_ARTIFACTS, MANIFEST_PATH, *REPORT_SOURCES)
        ],
        "targets": [
            str(SETTINGS.reports_dir / "build" / "main.pdf"),
            str(SETTINGS.reports_dir / "build" / "test_main.pdf"),
            str(SETTINGS.reports_dir / "build" / "latex_build.log"),
        ],
        "task_dep": [
            "generate_exhibits",
            "extension_generate_combined_report",
            "cay_lab_section9_chartbook",
        ],
    }


def task_run_tests():
    """Run deterministic tests and write JUnit XML."""
    SETTINGS.output_dir.mkdir(parents=True, exist_ok=True)
    return {
        "actions": [_run_tests_action],
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


def _build_extension_input_data() -> None:
    subprocess.run(
        [str(Path(sys.executable)), "cay_data/build_components_from_s14.py"],
        check=True,
    )
    subprocess.run(
        [str(Path(sys.executable)), "cay_data/build_extension_data.py"],
        check=True,
    )


def task_extension_build_input_data():
    """Build local extension decomposition CSV inputs under cay_data/."""
    return {
        "actions": [_build_extension_input_data],
        "task_dep": ["config"],
        "targets": [
            str(EXTENSION_SETTINGS.cay_data_dir / "cay_components_households_q.csv"),
            str(EXTENSION_SETTINGS.cay_data_dir / "cay_components_hnpo_q.csv"),
            str(EXTENSION_SETTINGS.cay_data_dir / "cay_components_wealth_groups_q.csv"),
            str(EXTENSION_REGION_SOURCE_CSV),
        ],
    }


def _run_extension_import_region_data() -> None:
    import_region_data(EXTENSION_SETTINGS)


def task_extension_import_region_data():
    """Stage 1: validate and normalise the extension region-proxy CSV."""
    return {
        "actions": [_run_extension_import_region_data],
        "file_dep": [str(EXTENSION_REGION_SOURCE_CSV)],
        "targets": [
            str(EXTENSION_REGION_NORMALIZED_PARQUET),
            str(EXTENSION_REGION_NORMALIZED_META),
        ],
        "task_dep": ["extension_build_input_data"],
    }


def _run_extension_build_panel() -> None:
    build_extension_panel(EXTENSION_SETTINGS)


def task_extension_build_panel():
    """Stage 2: build the extension predictivity panel."""
    return {
        "actions": [_run_extension_build_panel],
        "file_dep": [str(EXTENSION_REGION_NORMALIZED_PARQUET)],
        "targets": [str(EXTENSION_PANEL_PARQUET), str(EXTENSION_PANEL_META)],
        "task_dep": ["extension_import_region_data"],
    }


def _run_extension_generate_exhibits() -> None:
    generate_extension_exhibits(EXTENSION_SETTINGS)


def task_extension_generate_exhibits():
    """Stage 3: generate extension chartbook/CSV/QA artifacts."""
    return {
        "actions": [_run_extension_generate_exhibits],
        "file_dep": [str(EXTENSION_PANEL_PARQUET)],
        "targets": [str(path) for path in EXTENSION_EXHIBIT_ARTIFACTS],
        "task_dep": ["extension_build_panel"],
    }


def _run_extension_generate_combined_report() -> None:
    generate_combined_report(EXTENSION_SETTINGS)


def task_extension_generate_combined_report():
    """Stage 4: generate the extension LaTeX section used by Section 8."""
    return {
        "actions": [_run_extension_generate_combined_report],
        "file_dep": [str(EXTENSION_SETTINGS.output_dir / "extension_qa.json")],
        "targets": [str(EXTENSION_REPORT_TEX)],
        "task_dep": ["extension_generate_exhibits"],
    }


def _run_cay_lab_section9_chartbook() -> None:
    build_chartbook(
        cay_decomposition="house_wealth_groups",
        input_start="2023Q1",
        input_end="2026Q1",
        prediction_period=2,
        train_periods=8,
        min_history_periods=2,
        risky_ticker="QQQ",
        output_dir=str(SECTION9_CHARTBOOK_OUTPUT_DIR),
    )


def task_cay_lab_section9_chartbook():
    """Generate Section 9 worked-example CAY Lab chartbook artifacts."""
    return {
        "actions": [_run_cay_lab_section9_chartbook],
        "targets": [str(path) for path in SECTION9_CHARTBOOK_TARGETS],
        "task_dep": ["extension_build_input_data"],
    }


DOIT_CONFIG = {
    "default_tasks": [
        "generate_exhibits",
        "run_notebook",
        "compile_report",
        "run_tests",
    ]
}
