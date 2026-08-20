"""PyDoit workflow for the core CAY replication and report."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from src.bootstrap_real_data import bootstrap_real_data
from src.data.build_extension_s14 import build_s14_components
from src.data.build_extension_sources import (
    build_regional_proxy_dataset,
    build_wealth_group_dataset,
)
from src.data.build_sources import RAW_FILES, normalize_pulled_sources
from src.data.extension_acquisition import (
    acquire_extension_sources,
    extension_sources_current,
)
from src.data.import_local import import_local_source
from src.data.pull_author_cay import ensure_author_data
from src.data.source_registry import SOURCE_REGISTRY, required_panel_sources
from src.extension.chartbook import build_chartbook, write_section9_manifest
from src.extension.pipeline import (
    PANEL_STEM as EXTENSION_PANEL_STEM,
)
from src.extension.pipeline import (
    REGION_NORMALIZED_STEM,
    build_extension_panel,
    generate_combined_report,
    generate_extension_exhibits,
    import_region_data,
)
from src.pipeline import build_panel, generate_exhibits
from src.reporting.latex import compile_latex_report
from src.settings import load_settings

SETTINGS = load_settings([])
PANEL_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.parquet"
PANEL_METADATA_PATH = SETTINGS.data_dir / "processed" / "core_quarterly.metadata.json"
MANIFEST_PATH = SETTINGS.reports_dir / "build" / "artifact_manifest.json"
BOOTSTRAP_MARKER = SETTINGS.output_dir / "bootstrap_real_data.complete"
TARGETS_PATH = SETTINGS.project_root / "config" / "paper_targets.yml"
EXTENSION_REGION_SOURCE_CSV = (
    SETTINGS.extension_data_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
)
EXTENSION_REGION_NORMALIZED_PARQUET = (
    SETTINGS.extension_normalized_dir / f"{REGION_NORMALIZED_STEM}.parquet"
)
EXTENSION_REGION_NORMALIZED_META = (
    SETTINGS.extension_normalized_dir / f"{REGION_NORMALIZED_STEM}.metadata.json"
)
EXTENSION_PANEL_PARQUET = (
    SETTINGS.extension_processed_dir / f"{EXTENSION_PANEL_STEM}.parquet"
)
EXTENSION_PANEL_META = (
    SETTINGS.extension_processed_dir / f"{EXTENSION_PANEL_STEM}.metadata.json"
)
EXTENSION_REPORT_TEX = SETTINGS.extension_reports_dir / "extension_report.tex"
EXTENSION_EXHIBIT_ARTIFACTS = (
    SETTINGS.extension_output_dir / "extension_prepared.csv",
    SETTINGS.extension_output_dir / "extension_rolling.csv",
    SETTINGS.extension_output_dir / "extension_chartbook.pdf",
    SETTINGS.extension_output_dir / "extension_qa.json",
)
SECTION9_CHARTBOOK_OUTPUT_DIR = (
    SETTINGS.project_root / "_output" / "extension" / "section9"
)
SECTION9_CHARTBOOK_TARGETS = (
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_prepared.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_tests.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "subcay_predictivity_rolling.csv",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "chartbook_subcay_predictivity.pdf",
    SECTION9_CHARTBOOK_OUTPUT_DIR / "section9_manifest.json",
    SETTINGS.reports_dir / "paper" / "generated" / "section9_figures.tex",
)
SECTION9_QQQ_CACHE = SETTINGS.extension_raw_dir / "market" / "QQQ.csv"
EXTENSION_FRED_IDS = (
    "CASTHPI",
    "ILSTHPI",
    "TXSTHPI",
    "USSTHPI",
    "CAPCPI",
    "ILPCPI",
    "TXPCPI",
    "CAPOP",
    "ILPOP",
    "TXPOP",
)

REPORT_CONTRACT = yaml.safe_load(
    (SETTINGS.reports_dir / "report_contract.yml").read_text(encoding="utf-8")
)
CORE_EXHIBIT_PATHS = tuple(
    SETTINGS.reports_dir / relative
    for entry in REPORT_CONTRACT["exhibits"].values()
    for relative in entry["paths"].values()
    if relative.startswith(("tables/", "figures/"))
)
APPENDIX_IDS = (
    "table_iii_replication",
    "table_iii_updated",
    "table_vi_replication",
    "table_vi_updated",
    "table_r1_replication_audit",
)
GENERATED_ARTIFACTS = (
    *CORE_EXHIBIT_PATHS,
    *(
        SETTINGS.reports_dir / "tables" / "appendix" / f"{artifact_id}_detail.{suffix}"
        for artifact_id in APPENDIX_IDS
        for suffix in ("csv", "tex")
    ),
    SETTINGS.reports_dir / "paper" / "generated" / "report_metadata.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "replication_status.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "generated_captions.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "empirical_findings.tex",
    SETTINGS.reports_dir / "paper" / "generated" / "appendix_tables.tex",
    SETTINGS.reports_dir / "build" / "report_metadata.json",
    SETTINGS.reports_dir / "build" / "replication_status.txt",
    SETTINGS.reports_dir / "build" / "current_vintage_cay_comparison.csv",
    SETTINGS.reports_dir / "build" / "table_iii_source_diagnostics.json",
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
    directories = (
        SETTINGS.data_dir,
        SETTINGS.output_dir,
        SETTINGS.reports_dir,
        SETTINGS.extension_output_dir,
        SETTINGS.extension_reports_dir,
    )
    return {
        "actions": [SETTINGS.create_directories],
        "uptodate": [lambda: all(path.is_dir() for path in directories)],
    }


def task_pull_author_data():
    """Download and normalize pinned author validation files."""

    def pull_author_data():
        ensure_author_data(SETTINGS.data_dir / "normalized", vintage=SETTINGS.end_date)

    targets = [
        str(SETTINGS.data_dir / "normalized" / f"{filename}.{suffix}")
        for filename in ("paper_macro_quarterly", "posted_cay_quarterly")
        for suffix in ("parquet", "metadata.json")
    ]
    return {
        "actions": [pull_author_data],
        "task_dep": ["config"],
        "targets": targets,
        "uptodate": [lambda: all(Path(target).exists() for target in targets)],
    }


def task_import_sources():
    """Validate normalized local source substitutes."""

    available = {
        source_id: candidates
        for source_id, spec in SOURCE_REGISTRY.items()
        if (candidates := list(SETTINGS.p10_input_dir.glob(f"{spec.filename_stem}.*")))
    }

    def import_available_sources():
        for source_id in available:
            import_local_source(
                source_id,
                SETTINGS.p10_input_dir,
                SETTINGS.data_dir / "normalized",
                vintage=SETTINGS.end_date,
            )

    return {
        "actions": [import_available_sources],
        "file_dep": [str(path) for paths in available.values() for path in paths],
        "targets": [
            str(
                SETTINGS.data_dir
                / "normalized"
                / f"{SOURCE_REGISTRY[source_id].filename_stem}.{suffix}"
            )
            for source_id in available
            for suffix in ("parquet", "metadata.json")
        ],
        "task_dep": ["config"],
        "uptodate": [not available],
    }


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
        "file_dep": [
            str(SETTINGS.data_dir / "raw" / relative) for relative in RAW_FILES.values()
        ],
        "targets": [
            str(
                SETTINGS.data_dir
                / "normalized"
                / f"{SOURCE_REGISTRY[source_id].filename_stem}.{suffix}"
            )
            for source_id in (
                "core_macro",
                "sp_market",
                "crsp_market",
                "rates",
                "recessions",
            )
            for suffix in ("parquet", "metadata.json")
        ],
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
        "task_dep": [
            "pull_author_data",
            "import_sources",
            "normalize_pulled_sources",
        ],
    }


def task_generate_exhibits():
    """Generate all core pre-PDF report artifacts."""

    def generate():
        generate_exhibits(SETTINGS)

    return {
        "actions": [generate],
        "file_dep": [
            str(PANEL_PATH),
            str(PANEL_METADATA_PATH),
            str(TARGETS_PATH),
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
            str(Path(sys.executable)),
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
        compile_latex_report(SETTINGS.reports_dir)

    return {
        "actions": [compile_report],
        "file_dep": [
            str(path) for path in (*GENERATED_ARTIFACTS, MANIFEST_PATH, *REPORT_SOURCES)
        ]
        + [
            str(EXTENSION_REPORT_TEX),
            str(SECTION9_CHARTBOOK_TARGETS[-1]),
        ],
        "targets": [
            str(SETTINGS.reports_dir / "build" / "main.pdf"),
            str(SETTINGS.reports_dir / "build" / "latex_build.log"),
        ],
        "task_dep": [
            "generate_exhibits",
            "extension_region_report",
            "extension_section9_chartbook",
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


def _acquire_extension_data() -> None:
    acquire_extension_sources(SETTINGS)


def task_extension_acquire():
    """Acquire or import declared extension source caches."""
    return {
        "actions": [_acquire_extension_data],
        "targets": [
            str(SETTINGS.extension_raw_dir / "FRB_Z1_S14_b_Q.csv"),
            str(SETTINGS.extension_raw_dir / "FRB_Z1_S1M_b_Q.csv"),
            str(SETTINGS.extension_raw_dir / "dfa.zip"),
            str(SECTION9_QQQ_CACHE),
        ]
        + [
            str(SETTINGS.extension_raw_dir / f"fred_{series_id}.csv")
            for series_id in EXTENSION_FRED_IDS
        ],
        "task_dep": ["config"],
        "uptodate": [lambda: extension_sources_current(SETTINGS)],
    }


def _prepare_extension_data() -> None:
    allow_network = SETTINGS.extension_acquisition_mode == "latest"
    build_s14_components(SETTINGS.extension_raw_dir, SETTINGS.extension_normalized_dir)
    build_wealth_group_dataset(
        SETTINGS.extension_raw_dir,
        SETTINGS.extension_normalized_dir,
        allow_network=allow_network,
    )
    build_regional_proxy_dataset(
        SETTINGS.extension_raw_dir,
        SETTINGS.extension_normalized_dir,
        allow_network=allow_network,
    )
    import_region_data(SETTINGS)


def task_extension_prepare():
    """Build normalized extension components and region contracts."""
    return {
        "actions": [_prepare_extension_data],
        "file_dep": [
            str(SETTINGS.extension_raw_dir / "FRB_Z1_S14_b_Q.csv"),
            str(SETTINGS.extension_raw_dir / "FRB_Z1_S1M_b_Q.csv"),
            str(SETTINGS.extension_raw_dir / "dfa.zip"),
        ],
        "targets": [
            str(SETTINGS.extension_normalized_dir / "cay_components_households_q.csv"),
            str(SETTINGS.extension_normalized_dir / "cay_components_hnpo_q.csv"),
            str(
                SETTINGS.extension_normalized_dir / "cay_components_wealth_groups_q.csv"
            ),
            str(EXTENSION_REGION_SOURCE_CSV),
            str(EXTENSION_REGION_NORMALIZED_PARQUET),
            str(EXTENSION_REGION_NORMALIZED_META),
        ],
        "task_dep": ["extension_acquire"],
    }


def _analyze_extension_data() -> None:
    build_extension_panel(SETTINGS)
    generate_extension_exhibits(SETTINGS)


def task_extension_analyze():
    """Build the extension panel and analysis artifacts."""
    return {
        "actions": [_analyze_extension_data],
        "file_dep": [str(EXTENSION_REGION_NORMALIZED_PARQUET)],
        "targets": [
            str(EXTENSION_PANEL_PARQUET),
            str(EXTENSION_PANEL_META),
            *(str(path) for path in EXTENSION_EXHIBIT_ARTIFACTS),
        ],
        "task_dep": ["extension_prepare"],
    }


def _run_extension_generate_combined_report() -> None:
    generate_combined_report(SETTINGS)


def task_extension_region_report():
    """Stage 4: generate the extension LaTeX section used by Section 8."""
    return {
        "actions": [_run_extension_generate_combined_report],
        "file_dep": [
            str(SETTINGS.extension_output_dir / "extension_qa.json"),
            str(PANEL_PATH),
        ],
        "targets": [str(EXTENSION_REPORT_TEX)],
        "task_dep": ["extension_analyze", "build_panel"],
    }


def _run_extension_section9_chartbook() -> None:
    build_chartbook(
        cay_decomposition="house_wealth_groups",
        input_start="2023Q1",
        input_end="2026Q1",
        prediction_period=2,
        train_periods=8,
        min_history_periods=2,
        risky_ticker="QQQ",
        output_dir=str(SECTION9_CHARTBOOK_OUTPUT_DIR),
        cay_data_dir=str(SETTINGS.extension_normalized_dir),
        market_data_dir=str(SETTINGS.extension_raw_dir / "market"),
    )
    write_section9_manifest(
        SECTION9_CHARTBOOK_OUTPUT_DIR,
        SECTION9_QQQ_CACHE,
        SETTINGS.reports_dir / "paper" / "generated" / "section9_figures.tex",
    )


def task_extension_section9_chartbook():
    """Generate Section 9 worked-example CAY Lab chartbook artifacts."""
    return {
        "actions": [_run_extension_section9_chartbook],
        "file_dep": [
            str(
                SETTINGS.extension_normalized_dir / "cay_components_wealth_groups_q.csv"
            ),
            str(SECTION9_QQQ_CACHE),
        ],
        "targets": [str(path) for path in SECTION9_CHARTBOOK_TARGETS],
        "task_dep": ["extension_prepare"],
    }


DOIT_CONFIG = {
    "default_tasks": [
        "generate_exhibits",
        "run_notebook",
        "compile_report",
        "run_tests",
    ]
}
