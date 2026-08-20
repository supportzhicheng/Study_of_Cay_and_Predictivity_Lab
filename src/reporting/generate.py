"""Generate all 32 required pre-PDF report artifacts from a core panel."""

from __future__ import annotations

import json
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
from src.analysis.table_r1 import (
    FAIL_REQUIRES_DIAGNOSIS,
    PASS_REVISED_VINTAGE,
    PASS_STRICT,
    build_table_r1,
    load_paper_targets,
)
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


def _table_sample_text(frame: pd.DataFrame, unit: str) -> str:
    starts = sorted(frame["sample_start"].dropna().astype(str).unique())
    ends = sorted(frame["sample_end"].dropna().astype(str).unique())
    if not starts or not ends:
        raise ValueError(f"{unit.title()} results lack observed sample dates.")
    sample = f"{starts[0]}--{ends[-1]}"
    details = []
    if len(starts) > 1:
        details.append(f"starts {starts[0]}--{starts[-1]}")
    if len(ends) > 1:
        details.append(f"endpoints {ends[0]}--{ends[-1]}")
    if details:
        sample += f" ({unit}-specific {'; '.join(details)}; see table columns)"
    return sample


def _table_ii_takeaway(historical: TableIIResult, updated: TableIIResult) -> str:
    predictors = ["dividend_yield", "payout_ratio", "relative_bill_rate", "cay"]
    persistence = updated.summary.loc[predictors, "ar1"]
    most_persistent = persistence.idxmax()
    return (
        f"{most_persistent} is the most persistent updated predictor "
        f"(AR(1)={persistence[most_persistent]:.3f}). Updated cay has "
        f"AR(1)={updated.summary.loc['cay', 'ar1']:.3f} and standard deviation "
        f"{updated.summary.loc['cay', 'standard_deviation']:.3f}, versus "
        f"{historical.summary.loc['cay', 'ar1']:.3f} and "
        f"{historical.summary.loc['cay', 'standard_deviation']:.3f} historically."
    )


def _table_iii_takeaway(historical: pd.DataFrame, updated: pd.DataFrame) -> str:
    def cay_result(frame: pd.DataFrame) -> pd.Series:
        return frame.loc[(frame["row"] == 6) & (frame["term"] == "cay")].iloc[0]

    old = cay_result(historical)
    new = cay_result(updated)
    return (
        "For the univariate excess-return specification (row 6), the cay "
        f"coefficient is {old['coefficient']:.3f} historically "
        f"(t={old['t_statistic']:.2f}, adjusted R-squared={old['adjusted_r_squared']:.3f}) "
        f"and {new['coefficient']:.3f} in the updated sample "
        f"(t={new['t_statistic']:.2f}, adjusted R-squared={new['adjusted_r_squared']:.3f})."
    )


def _table_vi_takeaway(updated: pd.DataFrame) -> str:
    cay_rows = updated.loc[
        (updated["specification"] == 2) & (updated["term"] == "cay")
    ].drop_duplicates("horizon")
    consumption_rows = updated.loc[
        (updated["specification"] == 1) & (updated["term"] == "cay")
    ].drop_duplicates("horizon")
    strongest_return = cay_rows.loc[cay_rows["adjusted_r_squared"].idxmax()]
    strongest_consumption = consumption_rows.loc[
        consumption_rows["adjusted_r_squared"].idxmax()
    ]
    return (
        f"Updated cay has its strongest excess-return fit at {int(strongest_return['horizon'])} "
        f"quarters (adjusted R-squared={strongest_return['adjusted_r_squared']:.3f}); "
        f"the strongest consumption-growth fit is at {int(strongest_consumption['horizon'])} "
        f"quarters (adjusted R-squared={strongest_consumption['adjusted_r_squared']:.3f})."
    )


def _audit_takeaway(audit: pd.DataFrame) -> str:
    counts = audit["status"].value_counts()
    return (
        f"Audit counts are {int(counts.get(PASS_STRICT, 0))} strict, "
        f"{int(counts.get(PASS_REVISED_VINTAGE, 0))} revised-vintage, and "
        f"{int(counts.get(FAIL_REQUIRES_DIAGNOSIS, 0))} requiring diagnosis."
    )


def _write_table_iii_source_diagnostics(
    reports_dir: Path,
    selections: PanelConventions,
    table_iii: pd.DataFrame,
    table_vi: pd.DataFrame,
    audit: pd.DataFrame,
) -> Path:
    row_13 = table_iii.loc[table_iii["row"] == 13]
    diagnostics = {
        "historical_primary": {
            "risk_free_return": "CRSP 30-day Treasury bill t30ret",
            "term_spread": "10-year Treasury yield minus 3-month Treasury yield",
            "crsp_market_return": "CRSP vwretd",
            "quarterly_return": "sum of monthly log1p returns",
            "relative_bill_rate": "current bill return minus prior four-quarter mean",
            "hac_lags": "max(1, horizon - 1)",
        },
        "selected": {
            "risk_free": selections.risk_free.selected,
            "term_spread": selections.term_spread.selected,
        },
        "candidate_metrics": {
            "risk_free": selections.risk_free.candidate_metrics,
            "term_spread": selections.term_spread.candidate_metrics,
        },
        "row_13": {
            "sample_start": str(row_13["sample_start"].iloc[0]),
            "observations": int(row_13["observations"].iloc[0]),
            "hac_lags": int(row_13["hac_lags"].iloc[0]),
        },
        "table_vi_hac_lags": {
            str(int(horizon)): int(group["hac_lags"].iloc[0])
            for horizon, group in table_vi.groupby("horizon", sort=True)
        },
        "sensitivity_checks": {
            "vwretx": "ruled out; the historical source contract uses vwretd",
            "t90ret": "ruled out; the historical source contract uses t30ret",
            "return_arithmetic": "ruled out; monthly log1p returns are summed quarterly",
            "predictor_timing": "ruled out; date-t predictors forecast t+1 outcomes",
            "cay_calibration": "ruled out; historical CAY remains independently estimated DLS",
        },
        "audit_status_counts": {
            str(status): int(count)
            for status, count in audit["status"].value_counts().items()
        },
    }
    path = reports_dir / "build" / "table_iii_source_diagnostics.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


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
    panel_path: Path,
    panel_metadata_path: Path,
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
    diagnostics_path = _write_table_iii_source_diagnostics(
        reports_dir,
        selections,
        table_iii_historical,
        table_vi_historical,
        audit,
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

    figure_data = {
        "figure_1_replication": prepare_figure_1(historical),
        "figure_1_updated": prepare_figure_1(updated),
        "figure_s1_data_anatomy": prepare_figure_s1(updated),
    }
    for artifact_id, data in figure_data.items():
        figure = (
            plot_figure_s1(data)
            if artifact_id == "figure_s1_data_anatomy"
            else plot_figure_1(data)
        )
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

    sample_dates: dict[str, tuple[str, str] | str] = {
        "table_ii_replication": (
            str(table_ii_historical.sample_start),
            str(table_ii_historical.sample_end),
        ),
        "table_ii_updated": (
            str(table_ii_updated.sample_start),
            str(table_ii_updated.sample_end),
        ),
        "table_iii_replication": _table_sample_text(table_iii_historical, "row"),
        "table_iii_updated": _table_sample_text(table_iii_updated, "row"),
        "table_vi_replication": _table_sample_text(table_vi_historical, "horizon"),
        "table_vi_updated": _table_sample_text(table_vi_updated, "horizon"),
        "table_s1_core_data_summary": _table_sample_text(
            table_s1.coverage.rename(
                columns={
                    "first_quarter": "sample_start",
                    "last_quarter": "sample_end",
                }
            ),
            "variable",
        ),
        "table_r1_replication_audit": ("1952Q4", "1998Q3"),
        **{
            artifact_id: (str(data.index.min()), str(data.index.max()))
            for artifact_id, data in figure_data.items()
        },
    }
    calculated_takeaways = {
        "table_ii_updated": _table_ii_takeaway(table_ii_historical, table_ii_updated),
        "figure_1_updated": (
            "The updated displayed-sample contemporaneous cay-return correlation is "
            f"{figure_data['figure_1_updated']['cay'].corr(figure_data['figure_1_updated']['sp_excess_return']):.3f}; "
            "forecasting evidence is reported in Tables III and VI."
        ),
        "table_iii_updated": _table_iii_takeaway(
            table_iii_historical, table_iii_updated
        ),
        "table_vi_updated": _table_vi_takeaway(table_vi_updated),
        "table_s1_core_data_summary": table_s1.takeaway,
        "table_r1_replication_audit": _audit_takeaway(audit),
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
            diagnostics_path,
        ]
    )

    source_dependencies = [
        panel_path,
        panel_metadata_path,
        reports_dir / "captions.yml",
        targets_path,
        reports_dir / "report_contract.yml",
        reports_dir / "report_config.yml",
    ]
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
    if len(artifacts) != 33:
        raise RuntimeError(f"Expected 33 report artifacts, generated {len(artifacts)}.")
    return artifacts
