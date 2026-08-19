"""Figure 1 standardized CAY and excess-return data."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

FIGURE_1_COLUMNS = ("cay", "sp_excess_return", "nber_recession")


def prepare_figure_1(panel: pd.DataFrame) -> pd.DataFrame:
    """Standardize displayed series and retain aligned recession shading."""
    missing = sorted(set(FIGURE_1_COLUMNS) - set(panel.columns))
    if missing:
        raise ValueError(f"Figure 1 is missing columns: {missing}")
    sample = panel.loc[:, FIGURE_1_COLUMNS].dropna()
    if sample.empty:
        raise ValueError("Figure 1 has no complete observations.")
    result = sample.copy()
    for column in ("cay", "sp_excess_return"):
        standard_deviation = sample[column].std(ddof=1)
        if standard_deviation == 0:
            raise ValueError(f"Figure 1 column '{column}' has zero variance.")
        result[column] = (sample[column] - sample[column].mean()) / standard_deviation
    return result


def plot_figure_1(data: pd.DataFrame):
    """Render standardized CAY and returns with quarterly recession shading."""
    dates = data.index.to_timestamp(how="end")
    figure, axis = plt.subplots(figsize=(10, 5.5))
    axis.plot(dates, data["cay"], label="cay", color="#16697A", linewidth=1.5)
    axis.plot(
        dates,
        data["sp_excess_return"],
        label="S&P excess return",
        color="#B23A48",
        linewidth=1.0,
        alpha=0.9,
    )
    for date_value, recession in zip(dates, data["nber_recession"], strict=True):
        if recession:
            axis.axvspan(
                date_value - pd.offsets.QuarterBegin(startingMonth=1),
                date_value,
                color="#D9D9D9",
                alpha=0.55,
                linewidth=0,
            )
    axis.axhline(0, color="#333333", linewidth=0.7)
    axis.set_ylabel("Displayed-sample standard deviations")
    axis.legend(frameon=False, ncol=2)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    return figure
