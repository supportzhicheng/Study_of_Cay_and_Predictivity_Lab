"""Data loading and pre-processing utilities.

Provides helpers to:
- Load raw quarterly series (consumption, asset wealth, labour income,
  excess stock returns) from CSV or pandas DataFrames.
- Load decomposition data from ``cay_data/``.
- Build cleaned predictivity datasets with user-defined train length and
  prediction horizon.
- Apply standard log-transformations and de-trending.
- Generate a synthetic dataset for testing / demonstration.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Column name constants (used across the whole package)
# ---------------------------------------------------------------------------
COL_C = "c"  # log real consumption per capita
COL_A = "a"  # log real household net worth per capita
COL_Y = "y"  # log real labour income per capita
COL_ER = "er"  # excess log stock return (e.g., annual or quarterly)

COMPONENTS = ("housing", "financial", "liquid")
_DEFAULT_CAY_DATA_DIR = Path(__file__).resolve().parents[2] / "cay_data"
_DATASET_FILE_MAP = {
    "households": "cay_components_households_q.csv",
    "households_and_nonprofits": "cay_components_hnpo_q.csv",
    "wealth_groups": "cay_components_wealth_groups_q.csv",
    "region_proxy": "cay_components_region_ca_il_tx_q_proxy.csv",
}


def load_from_csv(path: str, date_col: str = "date", **kwargs) -> pd.DataFrame:
    """Load a CSV file and return a DataFrame indexed by a DatetimeIndex.

    Parameters
    ----------
    path:
        Path to the CSV file.
    date_col:
        Name of the column containing dates.
    **kwargs:
        Additional keyword arguments forwarded to :func:`pandas.read_csv`.

    Returns
    -------
    pd.DataFrame
        DataFrame with a :class:`pandas.DatetimeIndex`.
    """
    df = pd.read_csv(path, **kwargs)
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col).sort_index()
    return df


def load_cay_decomposition(
    dataset: str = "households_and_nonprofits",
    cay_data_dir: str | Path | None = None,
    start: str | None = None,
    end: str | None = None,
    dropna_components: bool = True,
) -> pd.DataFrame:
    """Load one decomposition panel from ``cay_data/``.

    Parameters
    ----------
    dataset:
        One of ``households``, ``households_and_nonprofits``,
        ``wealth_groups``, ``region_proxy``.
    cay_data_dir:
        Folder containing decomposition files. Defaults to repo ``cay_data/``.
    start, end:
        Optional quarter boundaries (e.g., ``"1989Q3"``).
    dropna_components:
        If True, drops rows with missing component values.

    Returns
    -------
    pd.DataFrame
        DataFrame indexed by quarterly :class:`pandas.PeriodIndex`.
    """
    if dataset not in _DATASET_FILE_MAP:
        valid = ", ".join(sorted(_DATASET_FILE_MAP))
        raise ValueError(f"Unknown dataset '{dataset}'. Valid options: {valid}")

    data_dir = Path(cay_data_dir) if cay_data_dir is not None else _DEFAULT_CAY_DATA_DIR
    file_path = data_dir / _DATASET_FILE_MAP[dataset]
    if not file_path.exists():
        raise FileNotFoundError(
            "Decomposition file not found: "
            f"{file_path}. This repository does not ship real decomposition "
            "datasets; generate local files with your own data credentials "
            "(for example via cay_data/build_components_from_s14.py and "
            "cay_data/build_extension_data.py)."
        )

    df = pd.read_csv(file_path)
    if "quarter" not in df.columns:
        raise ValueError(f"Expected column 'quarter' in {file_path.name}")

    df = df.copy()
    df["quarter"] = pd.PeriodIndex(df["quarter"].astype(str), freq="Q")
    df = df.set_index("quarter")

    if start is not None:
        df = df[df.index >= pd.Period(start, freq="Q")]
    if end is not None:
        df = df[df.index <= pd.Period(end, freq="Q")]

    component_cols = [
        col
        for col in df.columns
        if col.endswith("_wealth_million_usd")
        or col.endswith("_proxy_scaled_million_usd")
    ]
    if dropna_components and component_cols:
        df = df.dropna(subset=component_cols)

    sort_cols = [c for c in ("wealth_group", "region") if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols)
    df = df.sort_index()
    return df


def prepare_predictivity_dataset(
    dataset: str = "wealth_groups",
    train_periods: int = 40,
    prediction_window: int = 1,
    target_component: str = "financial",
    components: tuple[str, ...] = COMPONENTS,
    min_history_periods: int = 8,
    cay_data_dir: str | Path | None = None,
    start: str | None = None,
    end: str | None = None,
) -> pd.DataFrame:
    """Load decomposition data and build model-ready predictivity inputs.

    This function creates:
    - ``sub_cay_*`` predictors as log-level deviations from each segment's
      expanding historical mean.
    - ``target_future_growth`` as log growth over ``prediction_window``.

    Parameters
    ----------
    dataset:
        Decomposition panel to load.
    train_periods:
        Rolling training window length (in quarters). Stored in output metadata.
    prediction_window:
        Prediction horizon in quarters for future growth target.
    target_component:
        Component used for the dependent variable.
    components:
        Components used as predictors.
    min_history_periods:
        Minimum history for the expanding-mean sub-cay transform.
    cay_data_dir, start, end:
        Passed to :func:`load_cay_decomposition`.

    Returns
    -------
    pd.DataFrame
        Columns include ``segment``, ``target_future_growth`` and
        ``sub_cay_{component}``.
    """
    if train_periods <= 0:
        raise ValueError("train_periods must be positive.")
    if prediction_window <= 0:
        raise ValueError("prediction_window must be positive.")
    if min_history_periods <= 1:
        raise ValueError("min_history_periods must be greater than 1.")
    if target_component not in components:
        raise ValueError("target_component must be included in components.")

    panel = load_cay_decomposition(
        dataset=dataset,
        cay_data_dir=cay_data_dir,
        start=start,
        end=end,
        dropna_components=False,
    )
    panel = panel.copy()

    if "wealth_group" in panel.columns:
        panel["segment"] = panel["wealth_group"].astype(str)
    elif "region" in panel.columns:
        panel["segment"] = panel["region"].astype(str)
    else:
        panel["segment"] = "all"

    component_col_map = {}
    for comp in components:
        candidates = [
            f"{comp}_wealth_million_usd",
            f"{comp}_assets_million_usd",
            f"{comp}_proxy_scaled_million_usd",
        ]
        if comp == "liquid":
            candidates = [
                "liquid_assets_million_usd",
                "liquid_proxy_scaled_million_usd",
            ] + candidates

        found = next((col for col in candidates if col in panel.columns), None)
        if found is None:
            raise ValueError(
                f"Could not find component column for '{comp}' in dataset '{dataset}'."
            )
        component_col_map[comp] = found

    keep_cols = ["segment"] + list(component_col_map.values())
    out = panel[keep_cols].copy()
    out = out.sort_index()

    rows: list[pd.DataFrame] = []
    for segment, seg_df in out.groupby("segment", sort=True):
        seg_df = seg_df.sort_index().copy()

        for comp in components:
            raw_col = component_col_map[comp]
            log_col = np.log(seg_df[raw_col])
            hist_mean = log_col.expanding(min_periods=min_history_periods).mean()
            seg_df[f"sub_cay_{comp}"] = log_col - hist_mean

        target_raw = component_col_map[target_component]
        seg_df["target_future_growth"] = np.log(seg_df[target_raw]).shift(
            -prediction_window
        ) - np.log(seg_df[target_raw])
        rows.append(seg_df)

    final_df = pd.concat(rows).sort_index()
    predictor_cols = [f"sub_cay_{c}" for c in components]
    final_df = final_df.dropna(subset=predictor_cols + ["target_future_growth"])

    final_df.attrs["train_periods"] = train_periods
    final_df.attrs["prediction_window"] = prediction_window
    final_df.attrs["target_component"] = target_component
    final_df.attrs["dataset"] = dataset
    final_df.attrs["component_columns"] = component_col_map
    return final_df


def log_transform(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    """Return a copy of *df* with the specified columns log-transformed.

    Parameters
    ----------
    df:
        Input DataFrame.
    cols:
        Columns to transform.  If *None*, transforms ``[COL_C, COL_A, COL_Y]``.

    Returns
    -------
    pd.DataFrame
    """
    if cols is None:
        cols = [COL_C, COL_A, COL_Y]
    out = df.copy()
    for col in cols:
        if col in out.columns:
            out[col] = np.log(out[col])
    return out
