"""Generate configurable sub-CAY predictivity chartbooks."""

from __future__ import annotations

import time
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
    data_source: str,
) -> pd.Series:
    from pandas_datareader import data as web

    def _cache_path_for_ticker(ticker_symbol: str) -> Path:
        cache_dir = PROJECT_ROOT / "cay_data" / "raw" / "market_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{ticker_symbol}.csv"

    def _extract_price_series(
        raw_prices: pd.DataFrame, ticker_symbol: str
    ) -> pd.Series:
        if raw_prices.empty:
            raise RuntimeError(f"No market data returned for ticker '{ticker_symbol}'.")
        if not isinstance(raw_prices.index, pd.DatetimeIndex):
            raise RuntimeError(
                f"Market data index for ticker '{ticker_symbol}' is not DatetimeIndex."
            )
        raw_prices = raw_prices.sort_index()
        candidate_cols = ("Adj Close", "Close", "close")
        price_series: pd.Series | None = None
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
            price_col = next(
                (col for col in candidate_cols if col in raw_prices.columns),
                None,
            )
            if price_col is not None:
                price_series = raw_prices[price_col]

        if price_series is None:
            available_cols = ", ".join(str(c) for c in raw_prices.columns)
            raise RuntimeError(
                f"Market data for ticker '{ticker_symbol}' is missing a close price column. "
                f"Available columns: {available_cols}"
            )
        return pd.to_numeric(price_series, errors="coerce").dropna()

    def _load_cached_price_series(cache_path: Path, ticker_symbol: str) -> pd.Series:
        if not cache_path.exists():
            raise FileNotFoundError(f"Market cache file not found: {cache_path}")
        cached = pd.read_csv(cache_path)
        required = {"date", "price"}
        if not required.issubset(cached.columns):
            raise RuntimeError(
                f"Market cache file {cache_path} must contain columns: date, price"
            )
        date_index = pd.to_datetime(cached["date"], errors="coerce")
        price_series = pd.to_numeric(cached["price"], errors="coerce")
        out = pd.Series(
            price_series.values, index=date_index, name=ticker_symbol
        ).dropna()
        if out.empty:
            raise RuntimeError(f"Market cache file {cache_path} has no valid rows.")
        if out.index.tz is not None:
            out.index = out.index.tz_localize(None)
        return out

    ticker_clean = ticker.strip().upper()
    if not ticker_clean:
        raise ValueError("risky_ticker must not be empty when provided.")

    start_ts = pd.Period(start, freq="Q").to_timestamp(how="start") if start else None
    end_ts = pd.Period(end, freq="Q").to_timestamp(how="end") if end else None
    cache_path = _cache_path_for_ticker(ticker_clean)
    try:
        cached_prices = _load_cached_price_series(cache_path, ticker_clean)
        cached_quarters = cached_prices.index.to_period("Q")
        requested_start = pd.Period(start, freq="Q") if start else cached_quarters.min()
        requested_end = pd.Period(end, freq="Q") if end else cached_quarters.max()
        if (
            cached_quarters.min() <= requested_start
            and cached_quarters.max() >= requested_end
        ):
            quarterly_prices = cached_prices.resample("QE-DEC").last().dropna()
            quarterly_prices.index = quarterly_prices.index.to_period("Q")
            quarterly_prices.name = "risky_asset_price"
            return quarterly_prices
    except (FileNotFoundError, RuntimeError):
        pass

    try:
        raw_prices = web.DataReader(
            ticker_clean,
            data_source,
            start=start_ts,
            end=end_ts,
        )
        price_series = _extract_price_series(raw_prices, ticker_clean)
    except (NotImplementedError, RuntimeError, ValueError) as exc:
        try:
            import yfinance as yf
        except ImportError as import_exc:
            raise RuntimeError(
                "Risky-asset fallback requires yfinance when pandas-datareader "
                f"source '{data_source}' is unavailable."
            ) from import_exc

        end_download = None if end_ts is None else end_ts + pd.Timedelta(days=1)
        price_series = pd.Series(dtype=float)
        last_yf_error: RuntimeError | None = None
        for attempt in range(1, 6):
            try:
                raw_prices = yf.download(
                    ticker_clean,
                    start=start_ts,
                    end=end_download,
                    interval="1d",
                    progress=False,
                    auto_adjust=False,
                )
                if (
                    isinstance(raw_prices.index, pd.DatetimeIndex)
                    and raw_prices.index.tz is not None
                ):
                    raw_prices.index = raw_prices.index.tz_localize(None)
                price_series = _extract_price_series(raw_prices, ticker_clean)
                if not price_series.empty:
                    break
            except RuntimeError as yf_exc:
                last_yf_error = yf_exc
            time.sleep(min(2 * attempt, 8))

        if price_series.empty:
            try:
                price_series = _load_cached_price_series(cache_path, ticker_clean)
            except (FileNotFoundError, RuntimeError) as cache_exc:
                raise RuntimeError(
                    f"Unable to fetch market data for ticker '{ticker_clean}'. "
                    "Tried pandas-datareader and yfinance (rate limits/network may apply), "
                    f"last yfinance error: {last_yf_error or exc}. "
                    f"and could not use local cache at {cache_path}. "
                    "Create cache file with columns 'date,price' as a fallback."
                ) from cache_exc

    if not price_series.empty:
        cache_df = price_series.rename("price").to_frame()
        cache_df.index.name = "date"
        cache_df.to_csv(cache_path)
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
    cay_data_dir: str = str(PROJECT_ROOT / "cay_data"),
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
        cay_data_dir=cay_data_dir,
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
