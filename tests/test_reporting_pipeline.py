"""Integration test for the complete report artifact build."""

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


def test_complete_report_pipeline_writes_registered_artifacts(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    shutil.copytree(PROJECT_ROOT / "reports", reports_dir)
    targets_dir = tmp_path / "config"
    targets_dir.mkdir()
    targets_path = targets_dir / "paper_targets.yml"
    shutil.copy2(PROJECT_ROOT / "config" / "paper_targets.yml", targets_path)
    shutil.copy2(
        PROJECT_ROOT / "config" / "extension_sources.yml",
        targets_dir / "extension_sources.yml",
    )
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

    assert len(artifacts) >= 33
    assert len({path.resolve() for path in artifacts}) == len(artifacts)
    assert all(path.exists() and path.stat().st_size > 0 for path in artifacts)
    assert (
        len([path for path in (reports_dir / "tables").glob("*") if path.is_file()])
        == 16
    )
    assert len(list((reports_dir / "figures").glob("*"))) == 9
    assert (reports_dir / "paper" / "generated" / "appendix_tables.tex").exists()
    assert len(list((reports_dir / "tables" / "appendix").glob("*.tex"))) == 5
    for tex_path in (reports_dir / "tables").glob("*.tex"):
        assert "NaN" not in tex_path.read_text(encoding="utf-8")
        assert r"\resizebox{\textwidth}{!}" in tex_path.read_text(encoding="utf-8")

    table_2 = pd.read_csv(reports_dir / "tables" / "table_iii_replication.csv")
    table_5 = pd.read_csv(reports_dir / "tables" / "table_iii_updated.csv")
    table_3 = pd.read_csv(reports_dir / "tables" / "table_vi_replication.csv")
    table_6 = pd.read_csv(reports_dir / "tables" / "table_vi_updated.csv")
    assert table_2["Model"].tolist() == list(range(1, 14))
    assert table_5["Model"].tolist() == [2, 4, 6, 8, 13]
    assert len(table_3) == len(table_6) == 16

    manifest = json.loads(
        (reports_dir / "build" / "artifact_manifest.json").read_text(encoding="utf-8")
    )
    required_dependencies = {
        str(panel_path.relative_to(tmp_path)),
        str(panel_metadata_path.relative_to(tmp_path)),
        "reports/report_contract.yml",
    }
    assert all(
        required_dependencies <= set(entry["source_dependencies"])
        for entry in manifest["artifacts"]
    )

    report_metadata = json.loads(
        (reports_dir / "build" / "report_metadata.json").read_text(encoding="utf-8")
    )
    actual_endpoint = report_metadata["updated_latest_common_quarter"]
    captions = (
        reports_dir / "paper" / "generated" / "generated_captions.tex"
    ).read_text(encoding="utf-8")
    assert actual_endpoint in captions
    assert "most persistent updated predictor" in captions
    assert "requiring diagnosis" in captions
    findings = (
        reports_dir / "paper" / "generated" / "empirical_findings.tex"
    ).read_text(encoding="utf-8")
    for macro in (
        "HistoricalSummaryFinding",
        "HistoricalFigureFinding",
        "HistoricalShortHorizonFinding",
        "HistoricalLongHorizonFinding",
        "UpdatedSummaryFinding",
        "UpdatedFigureFinding",
        "UpdatedShortHorizonFinding",
        "UpdatedLongHorizonFinding",
        "DataCoverageFinding",
        "DataAnatomyFinding",
    ):
        assert rf"\newcommand{{\{macro}}}" in findings

    diagnostics = json.loads(
        (reports_dir / "build" / "table_iii_source_diagnostics.json").read_text(
            encoding="utf-8"
        )
    )
    assert diagnostics["selected"] == {
        "risk_free": "bill_30d",
        "term_spread": "term_10y_3m",
    }
    assert diagnostics["row_13"] == {
        "sample_start": "1953Q2",
        "observations": 181,
        "hac_lags": 1,
    }
    assert diagnostics["table_vi_hac_lags"] == {
        "1": 1,
        "2": 1,
        "3": 2,
        "4": 3,
        "8": 7,
        "12": 11,
        "16": 15,
        "24": 23,
    }
