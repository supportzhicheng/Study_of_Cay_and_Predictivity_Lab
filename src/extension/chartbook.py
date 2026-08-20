"""Generate configurable sub-CAY predictivity chartbooks."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from src.extension.loader import prepare_predictivity_dataset
from src.extension.predictivity import (
    rolling_predictivity as _rolling_predictivity,
)
from src.extension.predictivity import (
    segment_predictivity_tests as _segment_predictivity_tests,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "_output" / "extension"
SUB_CATEGORY_DATASET_MAP = {
    "asset_wealth": "households_and_nonprofits",
    "region": "region_proxy",
    "house_wealth_groups": "wealth_groups",
}
VALID_DATASETS = {
    "households",
    "households_and_nonprofits",
    "wealth_groups",
    "region_proxy",
}


def _normalize_choice(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_dataset_key(dataset: str, sub_category: str | None) -> str:
    if sub_category:
        normalized_sub_category = _normalize_choice(sub_category)
        if normalized_sub_category not in SUB_CATEGORY_DATASET_MAP:
            valid = ", ".join(sorted(SUB_CATEGORY_DATASET_MAP))
            raise ValueError(
                f"Unknown sub_category '{sub_category}'. Valid options: {valid}"
            )
        return SUB_CATEGORY_DATASET_MAP[normalized_sub_category]

    normalized_dataset = _normalize_choice(dataset)
    if normalized_dataset not in VALID_DATASETS:
        valid = ", ".join(sorted(VALID_DATASETS))
        raise ValueError(f"Unknown dataset '{dataset}'. Valid options: {valid}")
    return normalized_dataset


def _validate_period_bounds(start: str | None, end: str | None) -> None:
    if start is None or end is None:
        return
    start_period = pd.Period(start, freq="Q")
    end_period = pd.Period(end, freq="Q")
    if start_period > end_period:
        raise ValueError(
            f"Invalid sample period: start ({start}) must be <= end ({end})."
        )


def _parse_risky_tickers(
    risky_tickers: str | None,
    risky_ticker: str | None,
) -> list[str]:
    raw = risky_tickers if risky_tickers else risky_ticker
    if not raw:
        return []
    tokens = [token.strip().upper() for token in raw.split(",") if token.strip()]
    deduped: list[str] = []
    for token in tokens:
        if token not in deduped:
            deduped.append(token)
    return deduped


def _fetch_risky_asset_quarterly_prices(
    ticker: str,
    start: str | None,
    end: str | None,
    market_data_dir: Path,
) -> pd.Series:
    ticker_clean = ticker.strip().upper()
    if not ticker_clean:
        raise ValueError("risky_ticker must not be empty when provided.")
    cache_path = market_data_dir / f"{ticker_clean}.csv"
    if not cache_path.exists():
        raise FileNotFoundError(
            f"Declared market cache is missing: {cache_path}. Run extension_acquire."
        )
    cached = pd.read_csv(cache_path)
    if not {"date", "price"}.issubset(cached.columns):
        raise ValueError(
            f"Market cache must contain date and price columns: {cache_path}"
        )
    price_series = pd.Series(
        pd.to_numeric(cached["price"], errors="coerce").to_numpy(),
        index=pd.to_datetime(cached["date"], errors="coerce"),
        name=ticker_clean,
    ).dropna()
    quarterly_prices = (
        pd.to_numeric(price_series, errors="coerce")
        .dropna()
        .resample("QE-DEC")
        .last()
        .dropna()
    )
    if quarterly_prices.empty:
        raise RuntimeError(
            f"Quarterly close prices are empty for ticker '{ticker_clean}'."
        )
    requested_start = (
        pd.Period(start, freq="Q")
        if start
        else quarterly_prices.index.min().to_period("Q")
    )
    requested_end = (
        pd.Period(end, freq="Q") if end else quarterly_prices.index.max().to_period("Q")
    )
    quarterly_prices.index = quarterly_prices.index.to_period("Q")
    if (
        quarterly_prices.index.min() > requested_start
        or quarterly_prices.index.max() < requested_end
    ):
        raise ValueError(
            f"Market cache {cache_path} does not cover {requested_start} through {requested_end}."
        )
    quarterly_prices = quarterly_prices.loc[requested_start:requested_end]
    quarterly_prices.name = "risky_asset_price"
    return quarterly_prices


def _build_risky_asset_target(
    quarterly_prices: pd.Series | pd.DataFrame,
    prediction_window: int,
) -> pd.DataFrame:
    if prediction_window <= 0:
        raise ValueError("prediction_window must be positive.")
    if not isinstance(quarterly_prices.index, pd.PeriodIndex):
        raise ValueError("quarterly_prices must be indexed by a quarterly PeriodIndex.")
    if isinstance(quarterly_prices, pd.Series):
        target = np.log(quarterly_prices.shift(-prediction_window)) - np.log(
            quarterly_prices
        )
        return pd.DataFrame(
            {
                "risky_asset_price": quarterly_prices,
                "target_risky_return": target,
            }
        )
    component_targets = np.log(quarterly_prices.shift(-prediction_window)) - np.log(
        quarterly_prices
    )
    equal_weight_target = component_targets.mean(axis=1).rename("target_risky_return")
    return component_targets.add_prefix("target_risky_return_").assign(
        target_risky_return=equal_weight_target
    )


def write_predictivity_chartbook(
    prepared_df: pd.DataFrame,
    rolling_df: pd.DataFrame,
    predictor_cols: list[str],
    pdf_path: Path,
    sub_category: str | None,
    dataset: str,
    train_periods: int,
    prediction_window: int,
    target_component: str,
    target_label: str,
    start: str | None,
    end: str | None,
    risky_tickers: list[str] | None,
    title: str = "Sub-CAY Predictivity Chartbook",
) -> None:
    with PdfPages(pdf_path) as pdf:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        summary_lines = [
            title,
            "",
            f"Sub-category: {sub_category or 'custom dataset selection'}",
            f"Dataset: {dataset}",
            f"Sample period: {start or 'beginning'} to {end or 'latest'}",
            f"Training window (quarters): {train_periods}",
            f"Prediction horizon (quarters): {prediction_window}",
            f"Target component: {target_component}",
            f"Target series: {target_label}",
            f"Risky asset tickers: {', '.join(risky_tickers) if risky_tickers else '(not used)'}",
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
            axes[0, 0].plot(
                seg["quarter_idx"], seg["actual"], label="Actual", linewidth=1.6
            )
            axes[0, 0].plot(
                seg["quarter_idx"], seg["prediction"], label="Predicted", linewidth=1.2
            )
            axes[0, 0].set_title(f"{target_label}: actual vs predicted")
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
            status_txt = " | ".join(
                f"{k}: {v}" for k, v in sorted(status_counts.items())
            )
            axes[1, 1].set_title(f"Absolute forecast error\n{status_txt}")
            axes[1, 1].grid(alpha=0.3)

            for ax in axes.flat:
                ax.tick_params(axis="x", rotation=30, labelsize=8)

            fig.tight_layout(rect=(0, 0, 1, 0.95))
            pdf.savefig(fig)
            plt.close(fig)


def build_chartbook(
    sub_category: str = "house_wealth_groups",
    cay_decomposition: str = "",
    dataset: str = "wealth_groups",
    train_periods: int = 40,
    prediction_window: int = 1,
    prediction_period: int = 0,
    target_component: str = "financial",
    output_dir: str = str(DEFAULT_OUTPUT_DIR),
    min_history_periods: int = 8,
    start: str = "",
    input_start: str = "",
    end: str = "",
    input_end: str = "",
    risky_ticker: str = "",
    risky_tickers: str = "",
    risky_data_source: str = "stooq",
    component_data_dir: str = str(PROJECT_ROOT / "_data" / "normalized" / "extension"),
    market_data_dir: str = str(PROJECT_ROOT / "_data" / "raw" / "extension" / "market"),
) -> None:
    """Create model outputs and a PDF chartbook for sub-cay predictivity."""
    sub_category = (cay_decomposition or sub_category) or None
    start = (input_start or start) or None
    end = (input_end or end) or None
    if prediction_period > 0:
        prediction_window = prediction_period
    risky_ticker_list = _parse_risky_tickers(risky_tickers, risky_ticker)

    dataset_key = _resolve_dataset_key(dataset=dataset, sub_category=sub_category)
    _validate_period_bounds(start=start, end=end)

    out_dir = Path(output_dir)
    if not out_dir.is_absolute():
        out_dir = PROJECT_ROOT / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    prepared = prepare_predictivity_dataset(
        dataset=dataset_key,
        component_data_dir=component_data_dir,
        train_periods=train_periods,
        prediction_window=prediction_window,
        target_component=target_component,
        min_history_periods=min_history_periods,
        start=start,
        end=end,
    ).copy()
    target_col = "target_future_growth"
    target_label = f"{target_component} future log growth"
    if risky_ticker_list:
        risky_price_columns = []
        for ticker in risky_ticker_list:
            risky_price_columns.append(
                _fetch_risky_asset_quarterly_prices(
                    ticker=ticker,
                    start=start,
                    end=end,
                    market_data_dir=Path(market_data_dir),
                ).rename(ticker)
            )
        risky_prices = pd.concat(risky_price_columns, axis=1, join="inner").dropna()
        risky_target = _build_risky_asset_target(
            quarterly_prices=risky_prices,
            prediction_window=prediction_window,
        )
        prepared = prepared.join(risky_target, how="inner")
        prepared = prepared.dropna(subset=["target_risky_return"])
        target_col = "target_risky_return"
        target_label = (
            f"Equal-weight basket ({', '.join(risky_ticker_list)}) future log return"
        )
    if prepared.empty:
        raise RuntimeError(
            "No prepared observations remain after applying sample and target filters."
        )

    predictor_cols = [c for c in prepared.columns if c.startswith("sub_cay_")]
    if not predictor_cols:
        raise RuntimeError("No sub-cay predictor columns found in prepared dataset.")

    tests = _segment_predictivity_tests(
        prepared,
        predictor_cols=predictor_cols,
        target_col=target_col,
    )
    if tests.empty:
        raise RuntimeError(
            "No segment-level predictive regression tests were produced."
        )

    rolling = _rolling_predictivity(
        prepared,
        predictor_cols=predictor_cols,
        target_col=target_col,
        train_periods=train_periods,
    )
    if rolling.empty:
        raise RuntimeError(
            "No rolling results were produced. "
            "Try a shorter training window or a longer sample."
        )

    prepared_out = out_dir / "subcay_predictivity_prepared.csv"
    tests_out = out_dir / "subcay_predictivity_tests.csv"
    rolling_out = out_dir / "subcay_predictivity_rolling.csv"
    pdf_out = out_dir / "chartbook_subcay_predictivity.pdf"

    prepared_to_save = prepared.copy()
    prepared_to_save.index = prepared_to_save.index.astype(str)
    prepared_to_save.index.name = "quarter"
    prepared_to_save.to_csv(prepared_out)
    tests.to_csv(tests_out, index=False)
    rolling.to_csv(rolling_out, index=False)

    write_predictivity_chartbook(
        prepared_df=prepared,
        rolling_df=rolling,
        predictor_cols=predictor_cols,
        pdf_path=pdf_out,
        sub_category=sub_category,
        dataset=dataset_key,
        train_periods=train_periods,
        prediction_window=prediction_window,
        target_component=target_component,
        target_label=target_label,
        start=start,
        end=end,
        risky_tickers=risky_ticker_list or None,
    )


def write_section9_manifest(
    output_dir: Path,
    market_cache: Path,
    generated_tex: Path,
) -> tuple[Path, Path]:
    """Map chartbook pages to Section 9 segments and write labeled wrappers."""
    prepared = pd.read_csv(output_dir / "subcay_predictivity_prepared.csv")
    rolling = pd.read_csv(output_dir / "subcay_predictivity_rolling.csv")
    segments = sorted(prepared["segment"].unique())
    labels = {
        "bottom50": "fig:section9_bottom50",
        "middle40": "fig:section9_middle40",
        "top10": "fig:section9_top10",
    }
    titles = {
        "bottom50": "Bottom 50\\%: Two-Quarter QQQ Forecast Diagnostics",
        "middle40": "Middle 40\\%: Two-Quarter QQQ Forecast Diagnostics",
        "top10": "Top 10\\%: Two-Quarter QQQ Forecast Diagnostics",
    }
    source_hash = hashlib.sha256(market_cache.read_bytes()).hexdigest()
    entries = []
    tex = []
    for page, segment in enumerate(segments, start=2):
        segment_rows = prepared.loc[prepared["segment"] == segment]
        rolling_rows = rolling.loc[rolling["segment"] == segment]
        entry = {
            "segment": segment,
            "page": page,
            "label": labels[segment],
            "sample_start": str(segment_rows["quarter"].min()),
            "sample_end": str(segment_rows["quarter"].max()),
            "rolling_start": str(rolling_rows["quarter"].min()),
            "rolling_end": str(rolling_rows["quarter"].max()),
            "target": "two-quarter QQQ log return",
            "source_sha256": source_hash,
        }
        entries.append(entry)
        tex.extend(
            [
                r"\begin{figure}[htbp]",
                r"\centering",
                rf"\includegraphics[page={page},width=\linewidth]{{../../_output/extension/section9/chartbook_subcay_predictivity.pdf}}",
                rf"\caption{{{titles[segment]}. Sample: {entry['sample_start']}--{entry['sample_end']}. Source: Federal Reserve DFA wealth-group detail and pinned QQQ adjusted-close cache ({source_hash[:12]}...).}}",
                rf"\label{{{labels[segment]}}}",
                r"\end{figure}",
                r"\FloatBarrier",
                "",
            ]
        )
    manifest_path = output_dir / "section9_manifest.json"
    manifest_path.write_text(
        json.dumps({"figures": entries}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    generated_tex.parent.mkdir(parents=True, exist_ok=True)
    generated_tex.write_text("\n".join(tex), encoding="utf-8")
    return manifest_path, generated_tex
