"""doit tasks for the CAY extension (cay_components_region) pipeline.

The staged tasks mirror the replication workflow in the root ``dodo.py``:
  1. import_region_data     – validate & normalise raw region CSV
  2. build_extension_panel  – prepare predictivity panel (parquet)
  3. generate_extension_exhibits – run analysis, chartbook PDF + CSVs
  4. generate_combined_report    – write combined replication+extension .tex

Legacy ``chartbook`` task is preserved for backward compatibility and
now delegates to the staged pipeline (uses the prepared panel).

Usage:
    doit -f cay_lab/dodo.py                           # run all staged tasks
    doit -f cay_lab/dodo.py import_region_data
    doit -f cay_lab/dodo.py build_extension_panel
    doit -f cay_lab/dodo.py generate_extension_exhibits
    doit -f cay_lab/dodo.py generate_combined_report
    doit -f cay_lab/dodo.py chartbook --dataset wealth_groups
Legacy chartbook example:
    doit -f cay_lab/dodo.py chartbook \
      --cay-decomposition house_wealth_groups \
      --input-start 1990Q1 \
      --input-end 2020Q4 \
      --prediction-period 1 \
      --risky-ticker QQQ
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib.pyplot as plt  # noqa: E402  (kept for legacy task)
import pandas as pd  # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages  # noqa: E402
from statsmodels.tools import add_constant  # noqa: E402

from cay_lab.pipeline import (  # noqa: E402
    PANEL_STEM,
    REGION_NORMALIZED_STEM,
    build_extension_panel,
    generate_combined_report,
    generate_extension_exhibits,
    import_region_data,
)
from cay_lab.settings import load_extension_settings  # noqa: E402

SETTINGS = load_extension_settings()
REGION_NORMALIZED_PARQUET = SETTINGS.output_dir / f"{REGION_NORMALIZED_STEM}.parquet"
REGION_NORMALIZED_META = SETTINGS.output_dir / f"{REGION_NORMALIZED_STEM}.metadata.json"
PANEL_PARQUET = SETTINGS.output_dir / f"{PANEL_STEM}.parquet"
PANEL_META = SETTINGS.output_dir / f"{PANEL_STEM}.metadata.json"
EXTENSION_ARTIFACTS = [
    SETTINGS.output_dir / "extension_prepared.csv",
    SETTINGS.output_dir / "extension_rolling.csv",
    SETTINGS.output_dir / "extension_chartbook.pdf",
    SETTINGS.output_dir / "extension_qa.json",
]
COMBINED_REPORT = SETTINGS.reports_dir / "combined_replication_extension.tex"
REGION_SOURCE_CSV = (
    SETTINGS.cay_data_dir / "cay_components_region_ca_il_tx_q_proxy.csv"
)

from cay_lab.analysis.predictive_regression import PredictiveRegression  # noqa: E402
from cay_lab.data.loader import prepare_predictivity_dataset  # noqa: E402

DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "cay_lab" / "output"
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
    data_source: str,
) -> pd.Series:
    from pandas_datareader import data as web

    ticker_clean = ticker.strip().upper()
    if not ticker_clean:
        raise ValueError("risky_ticker must not be empty when provided.")

    start_ts = pd.Period(start, freq="Q").to_timestamp(how="start") if start else None
    end_ts = pd.Period(end, freq="Q").to_timestamp(how="end") if end else None
    try:
        raw_prices = web.DataReader(
            ticker_clean,
            data_source,
            start=start_ts,
            end=end_ts,
        )
    except NotImplementedError:
        if data_source not in {"stooq", "yahoo"}:
            raise
        try:
            import yfinance as yf
        except ImportError as exc:
            raise RuntimeError(
                "Risky-asset fallback requires yfinance when pandas-datareader "
                f"source '{data_source}' is unavailable."
            ) from exc

        end_download = None if end_ts is None else end_ts + pd.Timedelta(days=1)
        raw_prices = yf.download(
            ticker_clean,
            start=start_ts,
            end=end_download,
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
        if raw_prices.empty:
            raise RuntimeError(
                f"No market data returned for ticker '{ticker_clean}' "
                "from yfinance fallback."
            )
        if not isinstance(raw_prices.index, pd.DatetimeIndex):
            raise RuntimeError(
                f"Fallback market data index for ticker '{ticker_clean}' "
                "is not DatetimeIndex."
            )
        raw_prices.index = raw_prices.index.tz_localize(None)
    if raw_prices.empty:
        raise RuntimeError(
            f"No market data returned for ticker '{ticker_clean}' from '{data_source}'."
        )
    if not isinstance(raw_prices.index, pd.DatetimeIndex):
        raise RuntimeError(
            f"Market data index for ticker '{ticker_clean}' is not DatetimeIndex."
        )

    raw_prices = raw_prices.sort_index()
    price_series: pd.Series | None = None
    candidate_cols = ("Adj Close", "Close", "close")
    if isinstance(raw_prices.columns, pd.MultiIndex):
        level0 = set(raw_prices.columns.get_level_values(0))
        for candidate in candidate_cols:
            if candidate in level0:
                candidate_frame = raw_prices[candidate]
                if isinstance(candidate_frame, pd.DataFrame):
                    price_series = candidate_frame.iloc[:, 0]
                else:
                    price_series = candidate_frame
                break
    else:
        price_col = next((col for col in candidate_cols if col in raw_prices.columns), None)
        if price_col is not None:
            price_series = raw_prices[price_col]

    if price_series is None:
        available_cols = ", ".join(str(c) for c in raw_prices.columns)
        raise RuntimeError(
            f"Market data for ticker '{ticker_clean}' is missing a close price column. "
            f"Available columns: {available_cols}"
        )

    quarterly_prices = (
        pd.to_numeric(price_series, errors="coerce")
        .dropna()
        .resample("QE-DEC")
        .last()
        .dropna()
    )
    if quarterly_prices.empty:
        raise RuntimeError(
            f"Quarterly close prices are empty for ticker '{ticker_clean}' "
            f"from source '{data_source}'."
        )
    quarterly_prices.index = quarterly_prices.index.to_period("Q")
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
        target = np.log(quarterly_prices.shift(-prediction_window)) - np.log(quarterly_prices)
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


def _segment_predictivity_tests(
    df: pd.DataFrame,
    predictor_cols: list[str],
    target_col: str,
) -> pd.DataFrame:
    rows: list[dict] = []
    for segment, seg_df in df.groupby("segment", sort=True):
        seg_df = seg_df.sort_index()
        reg = PredictiveRegression(
            seg_df,
            target_col=target_col,
            predictor_cols=predictor_cols,
            horizon=0,
        )
        reg.fit()
        t_stats = {col: float(reg.t_stat(col)) for col in predictor_cols}
        max_abs_t = max(abs(v) for v in t_stats.values())
        row = {
            "segment": segment,
            "r_squared": float(reg.r_squared()),
            "n_obs": int(reg.result_.nobs),
            "status": _classify_status(max_abs_t),
            "target_col": target_col,
        }
        for col in predictor_cols:
            row[f"coef_{col}"] = float(reg.result_.params[col])
            row[f"t_stat_{col}"] = t_stats[col]
            row[f"p_value_{col}"] = float(reg.result_.pvalues[col])
        rows.append(row)
    return pd.DataFrame(rows).sort_values("segment").reset_index(drop=True)


def _write_chartbook(
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
) -> None:
    with PdfPages(pdf_path) as pdf:
        fig, ax = plt.subplots(figsize=(11, 8.5))
        ax.axis("off")
        summary_lines = [
            "Sub-CAY Predictivity Chartbook",
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
            axes[0, 0].plot(seg["quarter_idx"], seg["actual"], label="Actual", linewidth=1.6)
            axes[0, 0].plot(seg["quarter_idx"], seg["prediction"], label="Predicted", linewidth=1.2)
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
            status_txt = " | ".join(f"{k}: {v}" for k, v in sorted(status_counts.items()))
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
                    data_source=risky_data_source,
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
        raise RuntimeError("No segment-level predictive regression tests were produced.")

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

    _write_chartbook(
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


def task_chartbook():
    """Generate a sub-cay predictivity chartbook (CSV + PDF)."""
    targets = [
        str(DEFAULT_OUTPUT_DIR / "subcay_predictivity_prepared.csv"),
        str(DEFAULT_OUTPUT_DIR / "subcay_predictivity_tests.csv"),
        str(DEFAULT_OUTPUT_DIR / "subcay_predictivity_rolling.csv"),
        str(DEFAULT_OUTPUT_DIR / "chartbook_subcay_predictivity.pdf"),
    ]
    return {
        "actions": [(build_chartbook,)],
        "targets": targets,
        "params": [
            {
                "name": "sub_category",
                "long": "sub-category",
                "default": "house_wealth_groups",
                "type": str,
                "help": (
                    "User-facing CAY sub-category: "
                    "asset_wealth, region, house_wealth_groups"
                ),
            },
            {
                "name": "cay_decomposition",
                "long": "cay-decomposition",
                "default": "",
                "type": str,
                "help": (
                    "Primary decomposition option: "
                    "asset_wealth, region, house_wealth_groups"
                ),
            },
            {
                "name": "dataset",
                "long": "dataset",
                "default": "wealth_groups",
                "type": str,
                "help": (
                    "Dataset key override: households, households_and_nonprofits, "
                    "wealth_groups, region_proxy"
                ),
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
                "name": "prediction_period",
                "long": "prediction-period",
                "default": 0,
                "type": int,
                "help": "Alias of prediction-window (quarters); overrides when > 0",
            },
            {
                "name": "start",
                "long": "start",
                "default": "",
                "type": str,
                "help": "Sample start quarter (e.g., 1990Q1). Leave empty for full span.",
            },
            {
                "name": "input_start",
                "long": "input-start",
                "default": "",
                "type": str,
                "help": "Input range start quarter (alias of --start).",
            },
            {
                "name": "end",
                "long": "end",
                "default": "",
                "type": str,
                "help": "Sample end quarter (e.g., 2020Q4). Leave empty for full span.",
            },
            {
                "name": "input_end",
                "long": "input-end",
                "default": "",
                "type": str,
                "help": "Input range end quarter (alias of --end).",
            },
            {
                "name": "target_component",
                "long": "target-component",
                "default": "financial",
                "type": str,
                "help": "Target component: housing, financial, liquid",
            },
            {
                "name": "risky_ticker",
                "long": "risky-ticker",
                "default": "",
                "type": str,
                "help": (
                    "Single risky asset ticker (e.g., QQQ). "
                    "Use --risky-tickers for multiple assets."
                ),
            },
            {
                "name": "risky_tickers",
                "long": "risky-tickers",
                "default": "",
                "type": str,
                "help": (
                    "Comma-separated risky-asset tickers (e.g., QQQ or QQQ,SPY)."
                ),
            },
            {
                "name": "risky_data_source",
                "long": "risky-data-source",
                "default": "stooq",
                "type": str,
                "help": "pandas-datareader source for risky ticker data (default: stooq)",
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


# ---------------------------------------------------------------------------
# Staged pipeline tasks (mirrors root dodo.py structure)
# ---------------------------------------------------------------------------


def task_import_region_data():
    """Stage 1: Validate and normalise the region-proxy CSV to parquet.

    Analogous to ``task_normalize_pulled_sources`` in the root dodo.
    """
    return {
        "actions": [_run_import_region_data],
        "file_dep": [str(REGION_SOURCE_CSV)],
        "targets": [str(REGION_NORMALIZED_PARQUET), str(REGION_NORMALIZED_META)],
        "verbosity": 2,
    }


def task_build_extension_panel():
    """Stage 2: Build the predictivity panel from normalised region data.

    Analogous to ``task_build_panel`` in the root dodo.
    """
    return {
        "actions": [_run_build_extension_panel],
        "file_dep": [str(REGION_NORMALIZED_PARQUET)],
        "targets": [str(PANEL_PARQUET), str(PANEL_META)],
        "task_dep": ["import_region_data"],
        "verbosity": 2,
    }


def task_generate_extension_exhibits():
    """Stage 3: Run analysis and produce all extension artifacts.

    Analogous to ``task_generate_exhibits`` in the root dodo.
    Produces: extension_prepared.csv, extension_rolling.csv,
    extension_chartbook.pdf, extension_qa.json.
    """
    return {
        "actions": [_run_generate_extension_exhibits],
        "file_dep": [str(PANEL_PARQUET)],
        "targets": [str(p) for p in EXTENSION_ARTIFACTS],
        "task_dep": ["build_extension_panel"],
        "verbosity": 2,
    }


def task_generate_combined_report():
    """Stage 4: Write combined replication + extension LaTeX section.

    Analogous to the report stage in root dodo.
    """
    return {
        "actions": [_run_generate_combined_report],
        "file_dep": [str(SETTINGS.output_dir / "extension_qa.json")],
        "targets": [str(COMBINED_REPORT)],
        "task_dep": ["generate_extension_exhibits"],
        "verbosity": 2,
    }


DOIT_CONFIG = {
    "default_tasks": [
        "import_region_data",
        "build_extension_panel",
        "generate_extension_exhibits",
        "generate_combined_report",
    ]
}


def _run_import_region_data() -> bool:
    import_region_data(SETTINGS)
    return True


def _run_build_extension_panel() -> bool:
    build_extension_panel(SETTINGS)
    return True


def _run_generate_extension_exhibits() -> bool:
    generate_extension_exhibits(SETTINGS)
    return True


def _run_generate_combined_report() -> bool:
    generate_combined_report(SETTINGS)
    return True
