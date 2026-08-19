"""Original data-anatomy figure for macro levels and four-quarter growth."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def prepare_figure_s1(panel: pd.DataFrame) -> pd.DataFrame:
    """Build indexed macro levels and four-quarter log growth on a common sample."""
    required = ["c", "a", "y", "nber_recession"]
    missing = sorted(set(required) - set(panel.columns))
    if missing:
        raise ValueError(f"Figure S1 is missing columns: {missing}")
    sample = panel[required].dropna()
    if sample.empty:
        raise ValueError("Figure S1 has no complete macro observations.")
    result = pd.DataFrame(index=sample.index)
    for source, label in (
        ("c", "consumption"),
        ("y", "labor_income"),
        ("a", "net_worth"),
    ):
        result[f"{label}_indexed"] = 100 * np.exp(
            sample[source] - sample[source].iloc[0]
        )
        result[f"{label}_growth_4q"] = sample[source].diff(4)
    result["nber_recession"] = sample["nber_recession"]
    return result


def plot_figure_s1(data: pd.DataFrame):
    """Render indexed levels and four-quarter growth with the paper endpoint marker."""
    dates = data.index.to_timestamp(how="end")
    figure, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    colors = {
        "consumption": "#16697A",
        "labor_income": "#D17A22",
        "net_worth": "#6A4C93",
    }
    for label, color in colors.items():
        axes[0].plot(dates, data[f"{label}_indexed"], label=label, color=color)
        axes[1].plot(dates, data[f"{label}_growth_4q"], label=label, color=color)
    for axis in axes:
        for date_value, recession in zip(dates, data["nber_recession"], strict=True):
            if recession:
                axis.axvspan(
                    date_value - pd.offsets.QuarterBegin(startingMonth=1),
                    date_value,
                    color="#D9D9D9",
                    alpha=0.45,
                    linewidth=0,
                )
        axis.axvline(
            pd.Period("1998Q3", freq="Q").end_time, color="#333333", linestyle="--"
        )
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Index, first common quarter = 100")
    axes[1].set_ylabel("Four-quarter log growth")
    axes[0].legend(frameon=False, ncol=3)
    figure.tight_layout()
    return figure
