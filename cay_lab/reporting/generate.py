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
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from statsmodels.tools import add_constant

from cay_lab.analysis.predictive_regression import PredictiveRegression

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


def write_extension_report_section(
    ext_reports_dir: Path,
    replication_reports_dir: Path,
    settings: "ExtensionSettings",
) -> Path:
    """Write a LaTeX section combining replication summary + extension results.

    The replication section is included via ``\\input{}`` so its content is
    never duplicated or modified.  Extension tables/figures are embedded
    directly.
    """
    ext_reports_dir.mkdir(parents=True, exist_ok=True)

    repl_section = replication_reports_dir / "paper" / "sections" / "03_replication.tex"
    repl_input = (
        rf"\input{{{repl_section}}}" if repl_section.exists() else "% replication section not found"
    )

    qa_path = settings.output_dir / "extension_qa.json"
    qa: dict = {}
    if qa_path.exists():
        qa = json.loads(qa_path.read_text(encoding="utf-8"))

    segments_list = qa.get("segments", [])
    segments_str = ", ".join(str(s) for s in segments_list) if segments_list else "N/A"
    status_counts = qa.get("status_counts", {})
    status_str = "; ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))

    chartbook_path = settings.output_dir / "extension_chartbook.pdf"
    rolling_path = settings.output_dir / "extension_rolling.csv"

    # Use a relative path so the .tex file compiles portably on any machine.
    try:
        chartbook_rel = chartbook_path.relative_to(ext_reports_dir)
    except ValueError:
        # Falls back to absolute path when they share no common prefix (rare).
        chartbook_rel = chartbook_path

    tex = textwrap.dedent(
        rf"""
        % ============================================================
        %  Combined Replication + Extension Results Section
        %  Auto-generated by cay_lab.reporting.generate
        % ============================================================

        \section{{Replication Results}}

        {repl_input}

        % ============================================================
        \section{{Extension: Regional CAY Decomposition}}
        % ============================================================

        \subsection{{Overview}}

        This section extends the national-level CAY analysis by decomposing
        wealth components into state-level proxies for California, Illinois,
        and Texas using the \texttt{{cay\_components\_region}} dataset.
        The extension pipeline mirrors the replication workflow
        (acquire $\to$ normalise $\to$ panel $\to$ analysis $\to$ report)
        while preserving all replication artifacts unchanged.

        \subsection{{Data and Methodology}}

        Regional wealth proxies are derived by scaling national Households and
        Nonprofit Organisations (HNPO) quarterly components by within-state
        shares, estimated from FRED house price indices (HPI), per capita
        personal income, population, and (where available) FDIC branch deposit
        data.  The resulting panel covers regions: \textit{{{segments_str}}}.

        \subsection{{Predictivity Results}}

        Sub-CAY predictors are constructed as log-level deviations from each
        region's expanding historical mean.  A rolling OLS regression with
        Newey--West standard errors forecasts one-quarter-ahead wealth-component
        growth using a \textit{{{qa.get('train_periods', 'N/A')}}}-quarter
        training window.

        \begin{{figure}}[htbp]
          \centering
          \includegraphics[width=\linewidth]{{{chartbook_rel}}}
          \caption{{Sub-CAY predictivity chartbook for regional decomposition.
                    Each page shows actual vs.\ predicted future growth,
                    rolling in-sample $R^2$, rolling HAC $t$-statistics,
                    and absolute forecast error for one region.}}
          \label{{fig:ext_chartbook}}
        \end{{figure}}

        Rolling forecast QA summary: {status_str if status_str else 'no rolling results produced'}.
        Full rolling results are available in \texttt{{{rolling_path.name}}}.

        \subsection{{Comparison with National Results}}

        The regional decomposition complements the national CAY analysis:
        predictive signal strength varies across states and wealth components,
        suggesting heterogeneous local wealth dynamics.
        """
    ).strip() + "\n"

    out_path = ext_reports_dir / "combined_replication_extension.tex"
    out_path.write_text(tex, encoding="utf-8")
    return out_path
