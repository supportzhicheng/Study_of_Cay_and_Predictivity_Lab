"""doit tasks for sub-cay predictivity chartbook generation.

Usage example:
    doit -f cay_lab/dodo.py chartbook --dataset wealth_groups --train-periods 48 --prediction-window 1
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from statsmodels.tools import add_constant

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cay_lab.analysis.predictive_regression import PredictiveRegression  # noqa: E402
from cay_lab.data.loader import prepare_predictivity_dataset  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "cay_lab" / "output"


def _classify_status(max_abs_t: float, t_active: float = 1.96, t_weak: float = 1.28) -> str:
    if max_abs_t > t_active:
        return "ACTIVE"
    if max_abs_t > t_weak:
        return "WEAKENED"
    return "LOST"


def _rolling_predictivity(
    df: pd.DataFrame,
    predictor_cols: list[str],
    target_col: str,
    train_periods: int,
) -> pd.DataFrame:
    rows: list[dict] = []
    for segment, seg_df in df.groupby("segment", sort=True):
        seg_df = seg_df.sort_index()
        if len(seg_df) <= train_periods:
            continue

        for split in range(train_periods, len(seg_df)):
            train = seg_df.iloc[split - train_periods:split]
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

            row = {
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


def _write_chartbook(
    prepared_df: pd.DataFrame,
    rolling_df: pd.DataFrame,
    predictor_cols: list[str],
    pdf_path: Path,
    dataset: str,
    train_periods: int,
    prediction_window: int,
    target_component: str,
) -> None:
    with PdfPages(pdf_path) as pdf:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        summary_lines = [
            "Sub-CAY Predictivity Chartbook",
            "",
            f"Dataset: {dataset}",
            f"Training window (quarters): {train_periods}",
            f"Prediction horizon (quarters): {prediction_window}",
            f"Target component: {target_component}",
            f"Predictors: {', '.join(predictor_cols)}",
            "",
            f"Prepared observations: {len(prepared_df):,}",
            f"Rolling forecast observations: {len(rolling_df):,}",
            f"Segments: {prepared_df['segment'].nunique()}",
        ]
        ax.text(0.02, 0.98, "\n".join(summary_lines), va="top", ha="left", fontsize=12)
        pdf.savefig(fig, bbox_inches="tight")
        plt.close(fig)

        for segment in sorted(rolling_df["segment"].unique()):
            seg = rolling_df[rolling_df["segment"] == segment].copy()
            if seg.empty:
                continue
            seg["quarter_idx"] = pd.PeriodIndex(seg["quarter"], freq="Q").to_timestamp()

            fig, axes = plt.subplots(2, 2, figsize=(12, 8))
            fig.suptitle(f"Sub-CAY Predictivity: {segment}", fontsize=14)

            # Actual vs predicted
            axes[0, 0].plot(seg["quarter_idx"], seg["actual"], label="Actual", linewidth=1.6)
            axes[0, 0].plot(seg["quarter_idx"], seg["prediction"], label="Predicted", linewidth=1.2)
            axes[0, 0].set_title("Future growth: actual vs predicted")
            axes[0, 0].legend(fontsize=8)
            axes[0, 0].grid(alpha=0.3)

            # Rolling R2
            axes[0, 1].plot(seg["quarter_idx"], seg["r_squared"], color="#4C72B0")
            axes[0, 1].set_title("Rolling in-sample R²")
            axes[0, 1].grid(alpha=0.3)

            # Rolling t-stats by predictor
            for col in predictor_cols:
                axes[1, 0].plot(seg["quarter_idx"], seg[f"t_stat_{col}"], label=col)
            axes[1, 0].axhline(1.96, color="green", linestyle="--", linewidth=0.8)
            axes[1, 0].axhline(-1.96, color="green", linestyle="--", linewidth=0.8)
            axes[1, 0].axhline(0, color="black", linewidth=0.8)
            axes[1, 0].set_title("Rolling HAC t-stats")
            axes[1, 0].legend(fontsize=8)
            axes[1, 0].grid(alpha=0.3)

            # Rolling abs error and status counts
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


def build_chartbook(
    dataset: str = "wealth_groups",
    train_periods: int = 40,
    prediction_window: int = 1,
    target_component: str = "financial",
    output_dir: str = str(DEFAULT_OUTPUT_DIR),
    min_history_periods: int = 8,
) -> None:
    """Create model outputs and a PDF chartbook for sub-cay predictivity."""
    out_dir = Path(output_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    prepared = prepare_predictivity_dataset(
        dataset=dataset,
        train_periods=train_periods,
        prediction_window=prediction_window,
        target_component=target_component,
        min_history_periods=min_history_periods,
    ).copy()

    predictor_cols = [c for c in prepared.columns if c.startswith("sub_cay_")]
    if not predictor_cols:
        raise RuntimeError("No sub-cay predictor columns found in prepared dataset.")

    rolling = _rolling_predictivity(
        prepared,
        predictor_cols=predictor_cols,
        target_col="target_future_growth",
        train_periods=train_periods,
    )
    if rolling.empty:
        raise RuntimeError(
            "No rolling results were produced. "
            "Try a shorter training window or a longer sample."
        )

    prepared_out = out_dir / "subcay_predictivity_prepared.csv"
    rolling_out = out_dir / "subcay_predictivity_rolling.csv"
    pdf_out = out_dir / "chartbook_subcay_predictivity.pdf"

    prepared_to_save = prepared.copy()
    prepared_to_save.index = prepared_to_save.index.astype(str)
    prepared_to_save.index.name = "quarter"
    prepared_to_save.to_csv(prepared_out)
    rolling.to_csv(rolling_out, index=False)

    _write_chartbook(
        prepared_df=prepared,
        rolling_df=rolling,
        predictor_cols=predictor_cols,
        pdf_path=pdf_out,
        dataset=dataset,
        train_periods=train_periods,
        prediction_window=prediction_window,
        target_component=target_component,
    )


def task_chartbook():
    """Generate a sub-cay predictivity chartbook (CSV + PDF)."""
    targets = [
        str(DEFAULT_OUTPUT_DIR / "subcay_predictivity_prepared.csv"),
        str(DEFAULT_OUTPUT_DIR / "subcay_predictivity_rolling.csv"),
        str(DEFAULT_OUTPUT_DIR / "chartbook_subcay_predictivity.pdf"),
    ]
    return {
        "actions": [(build_chartbook,)],
        "targets": targets,
        "params": [
            {
                "name": "dataset",
                "long": "dataset",
                "default": "wealth_groups",
                "type": str,
                "help": "Dataset key: households, households_and_nonprofits, wealth_groups, region_proxy",
            },
            {
                "name": "train_periods",
                "long": "train-periods",
                "default": 40,
                "type": int,
                "help": "Rolling training window length in quarters",
            },
            {
                "name": "prediction_window",
                "long": "prediction-window",
                "default": 1,
                "type": int,
                "help": "Prediction horizon in quarters",
            },
            {
                "name": "target_component",
                "long": "target-component",
                "default": "financial",
                "type": str,
                "help": "Target component: housing, financial, liquid",
            },
            {
                "name": "output_dir",
                "long": "output-dir",
                "default": str(DEFAULT_OUTPUT_DIR),
                "type": str,
                "help": "Output folder for chartbook artifacts",
            },
            {
                "name": "min_history_periods",
                "long": "min-history-periods",
                "default": 8,
                "type": int,
                "help": "Minimum history for expanding-mean sub-cay transform",
            },
        ],
        "verbosity": 2,
    }
