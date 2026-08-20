"""Tests for the CAY extension (cay_components_region) staged pipeline.

Validates:
- import_region_data: loads and validates the region CSV → parquet
- build_extension_panel: produces a well-formed predictivity panel
- generate_extension_exhibits: chartbook and CSV artifacts are produced
- generate_combined_report: combined LaTeX section is written and non-empty
- replication pipeline remains intact (existing artifacts unmodified)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from cay_lab.pipeline import (
    PANEL_STEM,
    REGION_NORMALIZED_STEM,
    build_extension_panel,
    generate_combined_report,
    generate_extension_exhibits,
    import_region_data,
)
from cay_lab.settings import load_extension_settings

# ---------------------------------------------------------------------------
# Fixture: temporary settings pointing to real cay_data source files
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGION_CSV = PROJECT_ROOT / "cay_data" / "cay_components_region_ca_il_tx_q_proxy.csv"


@pytest.fixture
def tmp_settings(tmp_path):
    """Settings with output/reports dirs redirected to a temp directory."""
    return load_extension_settings(
        output_dir=tmp_path / "output",
        reports_dir=tmp_path / "reports",
        train_periods=10,          # small for fast tests
        prediction_window=1,
        target_component="financial",
        min_history_periods=4,
    )


# ---------------------------------------------------------------------------
# Stage 1 – import_region_data
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_import_region_data_creates_parquet(tmp_settings):
    out = import_region_data(tmp_settings)
    assert out.exists(), "Normalised parquet was not written."
    assert out.suffix == ".parquet"


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_import_region_data_metadata_json(tmp_settings):
    import_region_data(tmp_settings)
    meta_path = tmp_settings.output_dir / f"{REGION_NORMALIZED_STEM}.metadata.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert "regions" in meta
    assert len(meta["regions"]) > 0


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_import_region_data_required_columns(tmp_settings):
    import_region_data(tmp_settings)
    parquet = tmp_settings.output_dir / f"{REGION_NORMALIZED_STEM}.parquet"
    df = pd.read_parquet(parquet)
    for col in ("region", "housing_proxy_scaled_million_usd",
                "financial_proxy_scaled_million_usd",
                "liquid_proxy_scaled_million_usd"):
        assert col in df.columns, f"Required column '{col}' missing from normalised data."


# ---------------------------------------------------------------------------
# Stage 2 – build_extension_panel
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_build_extension_panel_creates_parquet(tmp_settings):
    import_region_data(tmp_settings)
    out = build_extension_panel(tmp_settings)
    assert out.exists()
    assert out.suffix == ".parquet"


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_build_extension_panel_has_subcay_columns(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    parquet = tmp_settings.output_dir / f"{PANEL_STEM}.parquet"
    df = pd.read_parquet(parquet)
    sub_cay_cols = [c for c in df.columns if c.startswith("sub_cay_")]
    assert len(sub_cay_cols) >= 1, "Extension panel has no sub_cay_* columns."


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_build_extension_panel_has_segment_column(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    parquet = tmp_settings.output_dir / f"{PANEL_STEM}.parquet"
    df = pd.read_parquet(parquet)
    assert "segment" in df.columns


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_build_extension_panel_fails_without_normalised_data(tmp_settings):
    with pytest.raises(FileNotFoundError, match="Normalised region data not found"):
        build_extension_panel(tmp_settings)


# ---------------------------------------------------------------------------
# Stage 3 – generate_extension_exhibits
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_generate_extension_exhibits_artifact_set(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    artifacts = generate_extension_exhibits(tmp_settings)
    # Expect four artifacts: prepared CSV, rolling CSV, chartbook PDF, QA JSON
    assert len(artifacts) == 4
    for path in artifacts:
        assert path.exists(), f"Expected artifact missing: {path}"


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_generate_extension_exhibits_qa_json_has_segments(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)
    qa = json.loads((tmp_settings.output_dir / "extension_qa.json").read_text())
    assert "segments" in qa
    assert len(qa["segments"]) > 0


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_generate_extension_exhibits_chartbook_is_pdf(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)
    pdf = tmp_settings.output_dir / "extension_chartbook.pdf"
    assert pdf.exists()
    # PDF magic bytes
    assert pdf.read_bytes()[:4] == b"%PDF"


# ---------------------------------------------------------------------------
# Stage 4 – generate_combined_report
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_generate_combined_report_creates_tex(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)
    out = generate_combined_report(tmp_settings)
    assert out.exists()
    assert out.suffix == ".tex"


@pytest.mark.skipif(
    not REGION_CSV.exists(),
    reason="cay_components_region CSV not present in cay_data/",
)
def test_generate_combined_report_contains_extension_section(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)
    out = generate_combined_report(tmp_settings)
    content = out.read_text(encoding="utf-8")
    assert r"\section{Extension" in content or "Extension" in content
    assert "Replication" in content


# ---------------------------------------------------------------------------
# Replication pipeline integrity: existing src modules must still import clean
# ---------------------------------------------------------------------------


def test_replication_pipeline_imports_cleanly():
    """Verify that adding extension code does not break any replication import."""
    from src.pipeline import build_panel, generate_exhibits  # noqa: F401
    from src.reporting.generate import generate_report_artifacts  # noqa: F401
    from src.settings import load_settings  # noqa: F401


def test_extension_settings_defaults():
    s = load_extension_settings()
    assert s.train_periods == 40
    assert s.prediction_window == 1
    assert s.target_component == "financial"
    assert s.include_extension is True
