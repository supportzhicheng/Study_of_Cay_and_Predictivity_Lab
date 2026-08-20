"""Synthetic integration tests for the staged extension pipeline."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.extension.pipeline import (
    PANEL_STEM,
    REGION_NORMALIZED_STEM,
    build_extension_panel,
    generate_combined_report,
    generate_extension_exhibits,
    import_region_data,
)
from src.settings import load_settings
from tests.test_reporting_pipeline import report_panel

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_region_fixture(path: Path) -> None:
    index = pd.period_range("1952Q4", periods=210, freq="Q")
    rows = []
    for region_index, region in enumerate(("California", "Illinois", "Texas"), 1):
        for period_index, quarter in enumerate(index, 1):
            base = 1000 + 10 * period_index + 100 * region_index
            rows.append(
                {
                    "quarter": str(quarter),
                    "region": region,
                    "housing_proxy_scaled_million_usd": base,
                    "financial_proxy_scaled_million_usd": 2 * base,
                    "liquid_proxy_scaled_million_usd": 0.5 * base,
                    "liquid_share_source": "income_share_fallback",
                }
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


@pytest.fixture
def tmp_settings(tmp_path: Path):
    settings = load_settings(
        argv=[
            "--EXTENSION_DATA_DIR",
            str(tmp_path / "_data" / "normalized" / "extension"),
            "--EXTENSION_RAW_DIR",
            str(tmp_path / "_data" / "raw" / "extension"),
            "--EXTENSION_NORMALIZED_DIR",
            str(tmp_path / "_data" / "normalized" / "extension"),
            "--EXTENSION_PROCESSED_DIR",
            str(tmp_path / "_data" / "processed" / "extension"),
            "--EXTENSION_OUTPUT_DIR",
            str(tmp_path / "_output" / "extension"),
            "--EXTENSION_REPORTS_DIR",
            str(tmp_path / "reports" / "paper" / "generated"),
            "--EXTENSION_TRAIN_PERIODS",
            "10",
            "--EXTENSION_MIN_HISTORY_PERIODS",
            "4",
        ],
        environ={},
        project_root=tmp_path,
    )
    _write_region_fixture(
        settings.extension_normalized_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "config" / "paper_targets.yml", config_dir)
    return settings


def test_import_region_data_writes_normalized_contract(tmp_settings):
    output = import_region_data(tmp_settings)
    metadata = json.loads(
        (
            tmp_settings.extension_normalized_dir
            / f"{REGION_NORMALIZED_STEM}.metadata.json"
        ).read_text()
    )

    assert output.exists()
    assert metadata["regions"] == ["California", "Illinois", "Texas"]


def test_build_extension_panel_uses_processed_root(tmp_settings):
    import_region_data(tmp_settings)
    output = build_extension_panel(tmp_settings)
    frame = pd.read_parquet(output)

    assert output == tmp_settings.extension_processed_dir / f"{PANEL_STEM}.parquet"
    assert "segment" in frame
    assert {column for column in frame if column.startswith("sub_cay_")}


def test_generate_extension_exhibits_writes_artifacts(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    artifacts = generate_extension_exhibits(tmp_settings)

    assert len(artifacts) == 4
    assert all(path.exists() and path.stat().st_size > 0 for path in artifacts)
    assert (tmp_settings.extension_output_dir / "extension_chartbook.pdf").read_bytes()[
        :4
    ] == b"%PDF"


def test_region_report_requires_core_panel(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)

    with pytest.raises(FileNotFoundError, match="core quarterly panel"):
        generate_combined_report(tmp_settings)


def test_region_report_builds_with_core_panel(tmp_settings):
    import_region_data(tmp_settings)
    build_extension_panel(tmp_settings)
    generate_extension_exhibits(tmp_settings)
    panel_path = tmp_settings.data_dir / "processed" / "core_quarterly.parquet"
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    panel = report_panel()
    panel["relative_bill_rate_30d"] = np.linspace(-0.01, 0.01, len(panel))
    panel.to_parquet(panel_path)

    output = generate_combined_report(tmp_settings)

    assert output == tmp_settings.extension_reports_dir / "extension_report.tex"
    assert "Replication-Style Results" in output.read_text(encoding="utf-8")


def test_extension_settings_defaults(tmp_path: Path):
    settings = load_settings(argv=[], environ={}, project_root=tmp_path)
    assert settings.extension_raw_dir == tmp_path / "_data" / "raw" / "extension"
    assert (
        settings.extension_normalized_dir
        == tmp_path / "_data" / "normalized" / "extension"
    )
    assert (
        settings.extension_processed_dir
        == tmp_path / "_data" / "processed" / "extension"
    )
    assert settings.extension_acquisition_mode == "latest"
