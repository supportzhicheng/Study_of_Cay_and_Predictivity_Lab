"""Deterministic synthetic datasets shared by tests."""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_dataset(
    n_periods: int = 200,
    seed: int = 42,
    start: str = "1970Q1",
) -> pd.DataFrame:
    """Generate cointegrated quarterly levels and partly predictable returns."""
    rng = np.random.default_rng(seed)
    index = pd.period_range(start=start, periods=n_periods, freq="Q")
    trend = np.cumsum(rng.normal(0, 1, n_periods))
    assets = trend + np.cumsum(rng.normal(0, 0.5, n_periods))
    income = trend + np.cumsum(rng.normal(0, 0.5, n_periods))
    cay = rng.normal(0, 0.5, n_periods)
    consumption = 0.3 * assets + 0.6 * income + cay
    excess_return = 1.5 * cay + rng.normal(0, 2, n_periods)
    return pd.DataFrame(
        {"c": consumption, "a": assets, "y": income, "er": excess_return},
        index=index,
    )
