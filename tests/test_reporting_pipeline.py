"""Integration test for the complete 32-artifact report build."""

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from src.reporting.generate import generate_report_artifacts

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def report_panel(periods: int = 210) -> pd.DataFrame:
    rng = np.random.default_rng(123)
    index = pd.period_range("1952Q4", periods=periods, freq="Q")
    trend = np.cumsum(rng.normal(scale=0.02, size=periods))
    c = trend + rng.normal(scale=0.03, size=periods)
    a = 1.4 * trend + rng.normal(scale=0.04, size=periods)
    y = 0.8 * trend + rng.normal(scale=0.03, size=periods)
    return pd.DataFrame(
        {
            "c": c,
            "a": a,
            "y": y,
            "paper_c": c + 0.01,
            "paper_a": a - 0.01,
            "paper_y": y + 0.02,
            "posted_cay": c - 0.31 * a - 0.59 * y,
            "sp_real_return": rng.normal(scale=0.1, size=periods),
            "crsp_vw_real_return": rng.normal(scale=0.1, size=periods),
            "sp_excess_return": rng.normal(scale=0.1, size=periods),
            "crsp_vw_excess_return": rng.normal(scale=0.1, size=periods),
            "bill_30d_return": rng.normal(scale=0.01, size=periods),
            "bill_3m_return": rng.normal(scale=0.01, size=periods),
            "relative_bill_rate_30d": rng.normal(scale=0.01, size=periods),
            "relative_bill_rate_3m": rng.normal(scale=0.01, size=periods),
            "term_spread_10y_3m": rng.normal(scale=0.01, size=periods),
            "term_spread_10y_1y": rng.normal(scale=0.01, size=periods),
            "default_spread": rng.normal(scale=0.01, size=periods),
            "dividend_yield": rng.normal(size=periods),
            "payout_ratio": rng.normal(size=periods),
            "nber_recession": (np.arange(periods) % 24 < 3).astype(int),
        },
        index=index,
    )


def test_complete_report_pipeline_writes_exactly_32_artifacts(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    shutil.copytree(PROJECT_ROOT / "reports", reports_dir)
    targets_dir = tmp_path / "config"
    targets_dir.mkdir()
    targets_path = targets_dir / "paper_targets.yml"
    shutil.copy2(PROJECT_ROOT / "config" / "paper_targets.yml", targets_path)
    processed_dir = tmp_path / "_data" / "processed"
    processed_dir.mkdir(parents=True)
    panel_path = processed_dir / "core_quarterly.parquet"
    panel_metadata_path = processed_dir / "core_quarterly.metadata.json"
    panel = report_panel()
    panel.to_parquet(panel_path)
    panel_metadata_path.write_text("{}\n", encoding="utf-8")

    artifacts = generate_report_artifacts(
        panel,
        reports_dir,
        targets_path,
        panel_path=panel_path,
        panel_metadata_path=panel_metadata_path,
        data_vintage="2026-08-18",
        git_commit="test-commit",
    )

    assert len(artifacts) == 32
    assert len({path.resolve() for path in artifacts}) == 32
    assert all(path.exists() and path.stat().st_size > 0 for path in artifacts)
    assert len(list((reports_dir / "tables").glob("*"))) == 16
    assert len(list((reports_dir / "figures").glob("*"))) == 9

    manifest = json.loads(
        (reports_dir / "build" / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    required_dependencies = {
        str(panel_path),
        str(panel_metadata_path),
        str(reports_dir / "captions.yml"),
    }
    assert all(
        required_dependencies <= set(entry["source_dependencies"])
        for entry in manifest["artifacts"]
    )

    table_iii = pd.read_csv(reports_dir / "tables" / "table_iii_updated.csv")
    actual_endpoint = table_iii["sample_end"].max()
    captions = (
        reports_dir / "paper" / "generated" / "generated_captions.tex"
    ).read_text(encoding="utf-8")
    assert actual_endpoint in captions
    assert "most persistent updated predictor" in captions
    assert "requiring diagnosis" in captions
