"""Generate all 32 required pre-PDF report artifacts from a core panel."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Mapping

import matplotlib.pyplot as plt
import pandas as pd
import yaml

from src.analysis.conventions import PanelConventions, select_panel_conventions
from src.analysis.exhibit_io import write_figure_artifacts, write_table_artifacts
from src.analysis.figure_1 import plot_figure_1, prepare_figure_1
from src.analysis.figure_s1 import plot_figure_s1, prepare_figure_s1
from src.analysis.modes import estimate_analysis_modes
from src.analysis.table_ii import TableIIResult, build_table_ii
from src.analysis.table_iii import build_table_iii
from src.analysis.table_r1 import build_table_r1, load_paper_targets
from src.analysis.table_s1 import TableS1Result, build_table_s1
from src.analysis.table_vi import build_table_vi
from src.data.build_quarterly_panel import HISTORICAL_INDEX, latest_common_quarter
from src.reporting.artifacts import write_artifact_manifest
from src.reporting.audit import write_replication_status
from src.reporting.captions import caption_macro_name, write_caption_macros
from src.reporting.metadata import write_report_metadata


def _apply_selected_conventions(
    panel: pd.DataFrame, selections: PanelConventions
) -> pd.DataFrame:
    result = panel.copy()
    bill_column, relative_column = {
        "bill_30d": ("bill_30d_return", "relative_bill_rate_30d"),
        "bill_3m": ("bill_3m_return", "relative_bill_rate_3m"),
    }[selections.risk_free.selected]
    term_column = {
        "term_10y_3m": "term_spread_10y_3m",
        "term_10y_1y": "term_spread_10y_1y",
    }[selections.term_spread.selected]
    result["relative_bill_rate"] = result[relative_column]
    result["term_spread"] = result[term_column]
    result["sp_excess_return"] = result["sp_real_return"] - result[bill_column]
    result["crsp_vw_excess_return"] = (
        result["crsp_vw_real_return"] - result[bill_column]
    )
    return result


def _table_ii_frame(result: TableIIResult) -> pd.DataFrame:
    correlations = result.correlations.reset_index(names="variable")
    correlations.insert(0, "panel", "correlations")
    summary = result.summary.reset_index(names="variable")
    summary.insert(0, "panel", "summary")
    return pd.concat([correlations, summary], ignore_index=True, sort=False)


def _table_s1_frame(result: TableS1Result) -> pd.DataFrame:
    coverage = result.coverage.copy()
    coverage.insert(0, "panel", "coverage")
    summary = result.summary.copy()
    summary.insert(0, "panel", "summary")
    return pd.concat([coverage, summary], ignore_index=True, sort=False)


def _caption_labels(reports_dir: Path) -> dict[str, str]:
    entries = yaml.safe_load((reports_dir / "captions.yml").read_text(encoding="utf-8"))
    return {artifact_id: entry["label"] for artifact_id, entry in entries.items()}


def _write_table(
    frame: pd.DataFrame,
    reports_dir: Path,
    artifact_id: str,
    labels: Mapping[str, str],
) -> list[Path]:
    paths = write_table_artifacts(
        frame,
        reports_dir / "tables",
        artifact_id,
        caption_macro=caption_macro_name(artifact_id),
        label=labels[artifact_id],
    )
    return [paths.csv, paths.tex]


def generate_report_artifacts(
    panel: pd.DataFrame,
    reports_dir: Path,
    targets_path: Path,
    *,
    data_vintage: str | None = None,
    git_commit: str = "UNKNOWN",
) -> list[Path]:
    """Generate the exact report artifact contract from observed panel data."""
    vintage = data_vintage or date.today().isoformat()
    targets = load_paper_targets(targets_path)
    modes = estimate_analysis_modes(panel, leads_lags=8)

    selection_panel = panel.reindex(HISTORICAL_INDEX).copy()
    selection_panel["cay"] = modes.paper_inputs.cay
    selections = select_panel_conventions(selection_panel, targets)
    canonical = _apply_selected_conventions(panel, selections)

    historical = canonical.reindex(HISTORICAL_INDEX).copy()
    historical[["c", "a", "y"]] = historical[["paper_c", "paper_a", "paper_y"]].rename(
        columns={"paper_c": "c", "paper_a": "a", "paper_y": "y"}
    )
    historical["cay"] = modes.paper_inputs.cay
    updated = canonical.copy()
    updated["cay"] = modes.updated.cay

    table_ii_historical = build_table_ii(historical)
    table_ii_updated = build_table_ii(updated)
    table_iii_historical = build_table_iii(historical)
    table_iii_updated = build_table_iii(updated)
    table_vi_historical = build_table_vi(historical)
    table_vi_updated = build_table_vi(updated)
    table_s1 = build_table_s1(updated)
    audit = build_table_r1(
        modes.paper_inputs,
        modes.historical_comparison,
        table_ii_historical,
        table_iii_historical,
        table_vi_historical,
        targets,
    )

    labels = _caption_labels(reports_dir)
    artifacts: list[Path] = []
    for artifact_id, frame in (
        ("table_ii_replication", _table_ii_frame(table_ii_historical)),
        ("table_ii_updated", _table_ii_frame(table_ii_updated)),
        ("table_iii_replication", table_iii_historical),
        ("table_iii_updated", table_iii_updated),
        ("table_vi_replication", table_vi_historical),
        ("table_vi_updated", table_vi_updated),
        ("table_s1_core_data_summary", _table_s1_frame(table_s1)),
        ("table_r1_replication_audit", audit),
    ):
        artifacts.extend(_write_table(frame, reports_dir, artifact_id, labels))

    figure_inputs = {
        "figure_1_replication": plot_figure_1(prepare_figure_1(historical)),
        "figure_1_updated": plot_figure_1(prepare_figure_1(updated)),
        "figure_s1_data_anatomy": plot_figure_s1(prepare_figure_s1(updated)),
    }
    for artifact_id, figure in figure_inputs.items():
        paths = write_figure_artifacts(
            figure,
            reports_dir / "figures",
            artifact_id,
            caption_macro=caption_macro_name(artifact_id),
            label=labels[artifact_id],
        )
        plt.close(figure)
        artifacts.extend([paths.pdf, paths.png, paths.tex])

    updated_end = latest_common_quarter(
        updated,
        ["cay", "sp_excess_return", "dividend_yield", "relative_bill_rate"],
    )
    metadata: dict[str, Any] = {
        "historical_sample_start": "1952Q4",
        "historical_sample_end": "1998Q3",
        "updated_latest_common_quarter": str(updated_end),
        "data_vintage": vintage,
        "cay_historical_primary": "estimated_dls",
        "cay_updated_primary": "estimated_dls",
        "cay_robustness": "fixed_ll_coefficients",
        "risk_free_primary": selections.risk_free.selected,
        "term_spread_primary": selections.term_spread.selected,
        "git_commit": git_commit,
    }
    metadata_json, metadata_tex = write_report_metadata(metadata, reports_dir)
    status_text, status_tex = write_replication_status(audit, reports_dir)
    comparison_path = reports_dir / "build" / "current_vintage_cay_comparison.csv"
    modes.historical_comparison.to_csv(comparison_path)

    sample_dates = {}
    for artifact_id in labels:
        if artifact_id.endswith("_updated"):
            sample_dates[artifact_id] = (str(updated.index.min()), str(updated_end))
        elif artifact_id in {"table_s1_core_data_summary", "figure_s1_data_anatomy"}:
            sample_dates[artifact_id] = (
                str(updated.index.min()),
                str(updated.index.max()),
            )
        else:
            sample_dates[artifact_id] = ("1952Q4", "1998Q3")
    calculated_takeaways = {
        "table_ii_updated": "Updated persistence and dispersion are calculated in the table.",
        "figure_1_updated": "Displayed co-movement is descriptive; forecasting tables provide formal evidence.",
        "table_iii_updated": "Updated coefficient precision is reported separately from replication quality.",
        "table_vi_updated": "The strongest updated horizon is identified from calculated adjusted R-squared values.",
        "table_s1_core_data_summary": table_s1.takeaway,
        "table_r1_replication_audit": audit["status"]
        .value_counts()
        .to_dict()
        .__str__(),
    }
    captions_tex = write_caption_macros(
        reports_dir / "captions.yml",
        reports_dir / "paper" / "generated" / "generated_captions.tex",
        sample_dates=sample_dates,
        data_vintage=vintage,
        calculated_takeaways=calculated_takeaways,
    )
    artifacts.extend(
        [
            metadata_tex,
            status_tex,
            captions_tex,
            metadata_json,
            status_text,
            comparison_path,
        ]
    )

    source_dependencies = [reports_dir / "report_contract.yml", targets_path]
    artifact_map = {
        f"artifact_{index:02d}": path for index, path in enumerate(artifacts, start=1)
    }
    dependency_map = {artifact_id: source_dependencies for artifact_id in artifact_map}
    manifest_path = write_artifact_manifest(
        artifact_map,
        dependency_map,
        reports_dir / "build" / "artifact_manifest.json",
        reports_dir / "schemas" / "artifact_manifest.schema.json",
        git_commit=git_commit,
    )
    artifacts.append(manifest_path)
    if len(artifacts) != 32:
        raise RuntimeError(f"Expected 32 report artifacts, generated {len(artifacts)}.")
    return artifacts
