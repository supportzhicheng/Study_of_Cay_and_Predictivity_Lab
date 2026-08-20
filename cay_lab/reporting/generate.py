"""Generate extension report artifacts (chartbook PDF + tables + combined section).

Provides the same artifact-generation contract as ``src/reporting/generate.py``
but for the ``cay_components_region`` extension analysis.  Replication artifacts
are never modified; this module only *adds* extension outputs.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from statsmodels.tools import add_constant

from cay_lab.analysis.predictive_regression import PredictiveRegression
from src.analysis.conventions import select_panel_conventions
from src.analysis.estimate_cay import estimate_cay
from src.analysis.figure_1 import plot_figure_1, prepare_figure_1
from src.analysis.modes import estimate_analysis_modes
from src.analysis.table_ii import TableIIResult, build_table_ii
from src.analysis.table_iii import build_table_iii
from src.analysis.table_r1 import load_paper_targets
from src.analysis.table_vi import build_table_vi
from src.data.build_quarterly_panel import HISTORICAL_INDEX, latest_common_quarter

if TYPE_CHECKING:
    from cay_lab.settings import ExtensionSettings


# ---------------------------------------------------------------------------
# Internal helpers shared with dodo.py
# ---------------------------------------------------------------------------


def _classify_status(max_abs_t: float, t_active: float = 1.96, t_weak: float = 1.28) -> str:
    if max_abs_t > t_active:
        return "ACTIVE"
    if max_abs_t > t_weak:
        return "WEAKENED"
    return "LOST"


def compute_rolling_predictivity(
    df: pd.DataFrame,
    predictor_cols: list[str],
    target_col: str,
    train_periods: int,
) -> pd.DataFrame:
    """Rolling one-period-ahead regression for every segment in *df*."""
    rows: list[dict] = []
    for segment, seg_df in df.groupby("segment", sort=True):
        seg_df = seg_df.sort_index()
        if len(seg_df) <= train_periods:
            continue

        for split in range(train_periods, len(seg_df)):
            train = seg_df.iloc[split - train_periods : split]
            test = seg_df.iloc[[split]]

            reg = PredictiveRegression(
                train,
                target_col=target_col,
                predictor_cols=predictor_cols,
                horizon=0,
            )
            reg.fit()

            x_test = add_constant(test[predictor_cols], has_constant="add")
            pred = float(reg.result_.predict(x_test).iloc[0])
            actual = float(test[target_col].iloc[0])
            t_stats = {col: float(reg.t_stat(col)) for col in predictor_cols}
            max_abs_t = max(abs(v) for v in t_stats.values())

            row: dict = {
                "quarter": str(test.index[0]),
                "segment": segment,
                "prediction": pred,
                "actual": actual,
                "error": actual - pred,
                "abs_error": abs(actual - pred),
                "r_squared": float(reg.r_squared()),
                "n_obs": int(reg.result_.nobs),
                "status": _classify_status(max_abs_t),
            }
            for col in predictor_cols:
                row[f"t_stat_{col}"] = t_stats[col]
                row[f"coef_{col}"] = float(reg.result_.params[col])
            rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Chartbook writer
# ---------------------------------------------------------------------------


def write_extension_chartbook(
    prepared_df: pd.DataFrame,
    rolling_df: pd.DataFrame,
    predictor_cols: list[str],
    pdf_path: Path,
    *,
    dataset: str,
    train_periods: int,
    prediction_window: int,
    target_component: str,
) -> None:
    """Write a multi-page PDF chartbook for the extension analysis."""
    with PdfPages(pdf_path) as pdf:
        # Cover page
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        lines = [
            "Sub-CAY Predictivity Chartbook — Extension (Region Proxy)",
            "",
            f"Dataset: {dataset}",
            f"Training window (quarters): {train_periods}",
            f"Prediction horizon (quarters): {prediction_window}",
            f"Target component: {target_component}",
            f"Predictors: {', '.join(predictor_cols)}",
            "",
            f"Prepared observations: {len(prepared_df):,}",
            f"Rolling forecast observations: {len(rolling_df):,}",
            f"Segments (regions): {prepared_df['segment'].nunique()}",
        ]
        ax.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", fontsize=12)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for segment in sorted(rolling_df["segment"].unique()):
            seg = rolling_df[rolling_df["segment"] == segment].copy()
            if seg.empty:
                continue
            seg["quarter_idx"] = pd.PeriodIndex(seg["quarter"], freq="Q").to_timestamp()

            fig, axes = plt.subplots(2, 2, figsize=(12, 8))
            fig.suptitle(f"Sub-CAY Predictivity: {segment}", fontsize=14)

            axes[0, 0].plot(seg["quarter_idx"], seg["actual"], label="Actual", linewidth=1.6)
            axes[0, 0].plot(seg["quarter_idx"], seg["prediction"], label="Predicted", linewidth=1.2)
            axes[0, 0].set_title("Future growth: actual vs predicted")
            axes[0, 0].legend(fontsize=8)
            axes[0, 0].grid(alpha=0.3)

            axes[0, 1].plot(seg["quarter_idx"], seg["r_squared"], color="#4C72B0")
            axes[0, 1].set_title("Rolling in-sample R²")
            axes[0, 1].grid(alpha=0.3)

            for col in predictor_cols:
                axes[1, 0].plot(seg["quarter_idx"], seg[f"t_stat_{col}"], label=col)
            axes[1, 0].axhline(1.96, color="green", linestyle="--", linewidth=0.8)
            axes[1, 0].axhline(-1.96, color="green", linestyle="--", linewidth=0.8)
            axes[1, 0].axhline(0, color="black", linewidth=0.8)
            axes[1, 0].set_title("Rolling HAC t-stats")
            axes[1, 0].legend(fontsize=8)
            axes[1, 0].grid(alpha=0.3)

            axes[1, 1].plot(seg["quarter_idx"], seg["abs_error"], color="#DD8452")
            status_counts = seg["status"].value_counts().to_dict()
            status_txt = " | ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))
            axes[1, 1].set_title(f"Absolute forecast error\n{status_txt}")
            axes[1, 1].grid(alpha=0.3)

            for ax in axes.flat:
                ax.tick_params(axis="x", rotation=30, labelsize=8)

            fig.tight_layout(rect=(0, 0, 1, 0.95))
            pdf.savefig(fig)
            plt.close(fig)


# ---------------------------------------------------------------------------
# Main exhibit-generation entry point
# ---------------------------------------------------------------------------

EXTENSION_ARTIFACT_STEMS = (
    "extension_prepared",
    "extension_rolling",
    "extension_chartbook",
    "extension_qa",
)

REGION_PROXY_COMPONENT_COLUMNS = (
    "housing_proxy_scaled_million_usd",
    "financial_proxy_scaled_million_usd",
    "liquid_proxy_scaled_million_usd",
)


def generate_extension_report_artifacts(
    panel: pd.DataFrame,
    settings: "ExtensionSettings",
) -> list[Path]:
    """Generate all extension report artifacts from the prepared panel.

    Produces:
    - ``extension_prepared.csv`` – model-ready panel (CSV mirror)
    - ``extension_rolling.csv``  – rolling forecast results
    - ``extension_chartbook.pdf`` – per-segment chartbook
    - ``extension_qa.json``      – QA / provenance metadata

    Returns a list of all written paths.
    """
    out_dir = settings.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    predictor_cols = [c for c in panel.columns if c.startswith("sub_cay_")]
    if not predictor_cols:
        raise RuntimeError(
            "No sub_cay_* predictor columns found in the extension panel. "
            "Ensure the 'panel' stage completed successfully."
        )

    # 1. Prepared CSV
    prepared_csv = out_dir / "extension_prepared.csv"
    panel_save = panel.copy()
    panel_save.index = panel_save.index.astype(str)
    panel_save.index.name = "quarter"
    panel_save.to_csv(prepared_csv)

    # 2. Rolling predictivity
    rolling_df = compute_rolling_predictivity(
        panel,
        predictor_cols=predictor_cols,
        target_col="target_future_growth",
        train_periods=settings.train_periods,
    )
    rolling_csv = out_dir / "extension_rolling.csv"
    rolling_df.to_csv(rolling_csv, index=False)

    # 3. Chartbook PDF
    pdf_path = out_dir / "extension_chartbook.pdf"
    if not rolling_df.empty:
        write_extension_chartbook(
            prepared_df=panel,
            rolling_df=rolling_df,
            predictor_cols=predictor_cols,
            pdf_path=pdf_path,
            dataset=settings.output_dir.name,
            train_periods=settings.train_periods,
            prediction_window=settings.prediction_window,
            target_component=settings.target_component,
        )
    else:
        # Write a stub PDF so downstream stages have a file to reference
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No rolling results (sample too short)", ha="center")
        ax.axis("off")
        with PdfPages(pdf_path) as pdf:
            pdf.savefig(fig)
        plt.close(fig)

    # 4. QA metadata
    status_counts: dict[str, int] = {}
    if not rolling_df.empty and "status" in rolling_df.columns:
        status_counts = rolling_df["status"].value_counts().to_dict()

    qa: dict[str, object] = {
        "dataset": "region_proxy",
        "segments": sorted(panel["segment"].unique().tolist()) if "segment" in panel.columns else [],
        "predictors": predictor_cols,
        "train_periods": settings.train_periods,
        "prediction_window": settings.prediction_window,
        "target_component": settings.target_component,
        "prepared_rows": len(panel),
        "rolling_rows": len(rolling_df),
        "status_counts": status_counts,
    }
    qa_path = out_dir / "extension_qa.json"
    qa_path.write_text(json.dumps(qa, indent=2) + "\n", encoding="utf-8")

    return [prepared_csv, rolling_csv, pdf_path, qa_path]


# ---------------------------------------------------------------------------
# Combined report section writer
# ---------------------------------------------------------------------------


def _apply_selected_conventions(
    panel: pd.DataFrame, targets_path: Path
) -> pd.DataFrame:
    targets = load_paper_targets(targets_path)
    modes = estimate_analysis_modes(panel, leads_lags=8)
    selection_panel = panel.reindex(HISTORICAL_INDEX).copy()
    selection_panel["cay"] = modes.paper_inputs.cay
    selections = select_panel_conventions(selection_panel, targets)
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
    result["crsp_vw_excess_return"] = result["crsp_vw_real_return"] - result[bill_column]
    return result


def _table_ii_frame(result: TableIIResult) -> pd.DataFrame:
    correlations = result.correlations.reset_index(names="variable")
    correlations.insert(0, "panel", "correlations")
    summary = result.summary.reset_index(names="variable")
    summary.insert(0, "panel", "summary")
    return pd.concat([correlations, summary], ignore_index=True, sort=False)


def _build_cay_r_series(core_panel: pd.DataFrame, region_csv_path: Path) -> pd.Series:
    region_raw = pd.read_csv(region_csv_path)
    required = {"quarter", *REGION_PROXY_COMPONENT_COLUMNS}
    missing = sorted(required - set(region_raw.columns))
    if missing:
        raise ValueError(
            f"Regional proxy CSV is missing required columns for cay_R: {missing}"
        )
    region_raw["quarter"] = pd.PeriodIndex(region_raw["quarter"].astype(str), freq="Q")
    region_panel = (
        region_raw.groupby("quarter")[list(REGION_PROXY_COMPONENT_COLUMNS)]
        .sum(min_count=1)
        .sort_index()
    )
    total_wealth_proxy = region_panel.sum(axis=1, min_count=1)
    if (total_wealth_proxy <= 0).any():
        raise ValueError("Regional wealth proxy contains non-positive values.")
    proxy_frame = pd.DataFrame(index=core_panel.index)
    proxy_frame["c"] = core_panel["c"]
    proxy_frame["y"] = core_panel["y"]
    proxy_frame["a"] = np.log(total_wealth_proxy).reindex(core_panel.index)
    proxy_frame = proxy_frame.dropna(subset=["c", "a", "y"])
    if proxy_frame.empty:
        raise ValueError("No overlapping quarterly sample to estimate cay_R.")
    return estimate_cay(proxy_frame, leads_lags=8).cay.rename("cay_R")


def _write_extension_replication_artifacts(
    ext_reports_dir: Path,
    core_panel_path: Path,
    region_csv_path: Path,
    targets_path: Path,
) -> dict[str, object]:
    panel = pd.read_parquet(core_panel_path)
    if not isinstance(panel.index, pd.PeriodIndex):
        panel.index = pd.PeriodIndex(panel.index, freq="Q")
    canonical = _apply_selected_conventions(panel, targets_path)
    cay_r = _build_cay_r_series(canonical, region_csv_path)
    extension_panel = canonical.copy()
    extension_panel["cay"] = cay_r.reindex(extension_panel.index)
    extension_panel = extension_panel.loc[
        : latest_common_quarter(
            extension_panel,
            ["cay", "sp_excess_return", "dividend_yield", "relative_bill_rate"],
        )
    ]

    table_ii = build_table_ii(extension_panel)
    table_iii = build_table_iii(extension_panel)
    table_vi = build_table_vi(extension_panel)
    figure_1 = prepare_figure_1(extension_panel)

    tables_dir = ext_reports_dir / "tables"
    figures_dir = ext_reports_dir / "figures"
    tables_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    table_ii_csv = tables_dir / "table_ii_extension_cay_r.csv"
    table_ii_tex = tables_dir / "table_ii_extension_cay_r.tex"
    table_iii_csv = tables_dir / "table_iii_extension_cay_r.csv"
    table_iii_tex = tables_dir / "table_iii_extension_cay_r.tex"
    table_vi_csv = tables_dir / "table_vi_extension_cay_r.csv"
    table_vi_tex = tables_dir / "table_vi_extension_cay_r.tex"

    _table_ii_frame(table_ii).to_csv(table_ii_csv, index=False)
    _table_ii_frame(table_ii).to_latex(table_ii_tex, index=False, escape=True)
    table_iii.to_csv(table_iii_csv, index=False)
    table_iii.to_latex(table_iii_tex, index=False, escape=True)
    table_vi.to_csv(table_vi_csv, index=False)
    table_vi.to_latex(table_vi_tex, index=False, escape=True)

    figure = plot_figure_1(figure_1)
    figure_pdf = figures_dir / "figure_1_extension_cay_r.pdf"
    figure_png = figures_dir / "figure_1_extension_cay_r.png"
    figure_tex = figures_dir / "figure_1_extension_cay_r.tex"
    figure.savefig(figure_pdf, bbox_inches="tight")
    figure.savefig(figure_png, dpi=180, bbox_inches="tight")
    plt.close(figure)
    figure_tex.write_text(
        "\n".join(
            [
                r"\begin{figure}[htbp]",
                r"\centering",
                r"\includegraphics[width=\linewidth]{../../cay_lab/output/reports/figures/figure_1_extension_cay_r.pdf}",
                r"\caption{Standardized $cay_R$ and excess S\&P returns.}",
                r"\label{fig:figure_1_extension_cay_r}",
                r"\end{figure}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "sample_start": str(figure_1.index.min()),
        "sample_end": str(figure_1.index.max()),
        "table_ii_tex": table_ii_tex,
        "figure_1_tex": figure_tex,
        "table_iii_tex": table_iii_tex,
        "table_vi_tex": table_vi_tex,
    }


def write_extension_report_section(
    ext_reports_dir: Path,
    replication_reports_dir: Path,
    settings: "ExtensionSettings",
) -> Path:
    """Write extension-only LaTeX content for the main report section 08."""
    ext_reports_dir.mkdir(parents=True, exist_ok=True)

    qa_path = settings.output_dir / "extension_qa.json"
    qa: dict = {}
    if qa_path.exists():
        qa = json.loads(qa_path.read_text(encoding="utf-8"))

    segments_list = qa.get("segments", [])
    segments_str = ", ".join(str(s) for s in segments_list) if segments_list else "N/A"
    status_counts = qa.get("status_counts", {})
    status_str = "; ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))

    core_panel_candidates = (
        settings.project_root / "_data" / "processed" / "core_quarterly.parquet",
        settings.project_root / "data" / "processed" / "core_quarterly.parquet",
    )
    core_panel_path = next((p for p in core_panel_candidates if p.exists()), core_panel_candidates[0])
    region_csv_path = settings.cay_data_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
    targets_path = settings.project_root / "config" / "paper_targets.yml"

    extension_exhibit_inputs = ""
    sample_window = "N/A"
    if core_panel_path.exists():
        extension_outputs = _write_extension_replication_artifacts(
            ext_reports_dir,
            core_panel_path,
            region_csv_path,
            targets_path,
        )
        sample_window = (
            f"{extension_outputs['sample_start']}--{extension_outputs['sample_end']}"
        )
        extension_exhibit_inputs = textwrap.dedent(
            r"""
            \subsection{Replication-Style Results with $cay_R$}
            \input{../../cay_lab/output/reports/tables/table_ii_extension_cay_r.tex}
            \input{../../cay_lab/output/reports/figures/figure_1_extension_cay_r.tex}
            \input{../../cay_lab/output/reports/tables/table_iii_extension_cay_r.tex}
            \input{../../cay_lab/output/reports/tables/table_vi_extension_cay_r.tex}
            """
        ).strip()
    else:
        extension_exhibit_inputs = (
            r"\textbf{Extension exhibits unavailable:} run the core panel and "
            r"\texttt{doit -f cay\_lab/dodo.py generate\_combined\_report}."
        )

    tex = textwrap.dedent(
        rf"""
        % ============================================================
        %  Combined Replication + Extension Results Section
        %  Auto-generated by cay_lab.reporting.generate
        % ============================================================

        \subsection{{Overview}}

        This extension constructs a Regional Replication predictor, denoted $cay_R$,
        from \texttt{{cay\_components\_region\_ca\_il\_tx\_q\_proxy.csv}} and
        reruns the replication-style forecasting pipeline with the
        \textit{{same model specifications}} used in the main report,
        replacing only the $cay$ construction.

        \subsection{{Data and Methodology}}

        Regional wealth proxies are derived by scaling national Households and
        Nonprofit Organisations (HNPO) quarterly components by within-state
        shares for California, Illinois, and Texas. We aggregate the regional
        proxy wealth levels by quarter, map them to the asset-wealth term in
        the DLS cointegrating regression, and estimate $cay_R$ with the same
        lead/lag settings as the baseline pipeline.

        \subsection{{Coverage}}

        Regions included: \textit{{{segments_str}}}.  Estimated $cay_R$ sample:
        \textit{{{sample_window}}}. Rolling extension QA summary:
        {status_str if status_str else 'no rolling results produced'}.

        {extension_exhibit_inputs}

        \subsection{{How to Read the Extension Figure}}

        Figure \ref{{fig:figure_1_extension_cay_r}} follows the same display
        convention as the replication figure.  Both lines are standardized in
        displayed-sample units, so crossings indicate relative (not level)
        comovement.  Gray recession shading marks NBER downturn quarters.
        Sustained periods where $cay_R$ leads excess-return reversals are the
        visual counterpart to the predictive-regression coefficients reported in
        Tables III and VI; statistical significance should be assessed from those
        tables rather than from line overlap alone.

        Full rolling chartbook outputs remain available in
        \texttt{{extension\_chartbook.pdf}}
        and \texttt{{extension\_rolling.csv}}.

        \subsection{{Comparison with National Results}}

        Relative to baseline exhibits, this section isolates the impact of
        replacing $cay$ with $cay_R$ while preserving the same downstream
        regressions, horizons, and plotting conventions.
        """
    ).strip() + "\n"

    out_path = ext_reports_dir / "combined_replication_extension.tex"
    out_path.write_text(tex, encoding="utf-8")
    return out_path
