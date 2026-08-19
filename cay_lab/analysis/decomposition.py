"""Decompose CAY to identify the real driver of predictivity.

Strategy
--------
CAY = c_t - β_a·a_t - β_y·y_t - const

We decompose the *predictive power* of CAY by asking: which individual
component (c alone, a alone, y alone) and which pair drives the
predictability of excess returns?

Specifically, for each subset ``S ⊆ {c, a, y}`` we run a predictive
regression

    er_{t+1} = α + γ_S · X_{S,t} + ε_{t+1}

and record the R².  The Shapley-value decomposition of the full-model
R² across the three predictors gives a model-free attribution of
predictive contribution.

Additionally, we track the sign and significance of each component's
coefficient when entered individually or jointly.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Optional

import pandas as pd

from cay_lab.analysis.cay_builder import CayBuilder
from cay_lab.analysis.predictive_regression import PredictiveRegression


class CayDecomposer:
    """Decompose the predictive power of CAY across its components.

    Parameters
    ----------
    df:
        DataFrame with columns ``c``, ``a``, ``y``, and the excess-return
        column identified by *excess_returns_col*.
    excess_returns_col:
        Name of the excess-return column (default ``'er'``).
    cay_lags:
        Lags used for the DOLS cointegration step in :class:`CayBuilder`.
    horizon:
        Forecast horizon for predictive regressions.

    Attributes (after :meth:`fit`)
    --------------------------------
    cay_builder_ : CayBuilder
    results_ : pd.DataFrame
        One row per predictor subset, with columns
        ``predictors``, ``r_squared``, ``n_obs``.
    shapley_ : pd.Series
        Shapley-value R² attribution for ``c``, ``a``, ``y``.
    """

    _COMPONENTS = ["c", "a", "y"]

    def __init__(
        self,
        df: pd.DataFrame,
        excess_returns_col: str = "er",
        cay_lags: int = 2,
        horizon: int = 1,
    ):
        self._df = df.copy()
        self.er_col = excess_returns_col
        self.cay_lags = cay_lags
        self.horizon = horizon
        self.cay_builder_: Optional[CayBuilder] = None
        self.results_: Optional[pd.DataFrame] = None
        self.shapley_: Optional[pd.Series] = None

    # ------------------------------------------------------------------
    def fit(self) -> "CayDecomposer":
        """Run all regressions and compute Shapley-value attribution."""
        # Step 1: build CAY
        builder = CayBuilder(self._df, lags=self.cay_lags)
        builder.fit()
        self.cay_builder_ = builder

        # Add cay column to working dataframe
        df = self._df.copy()
        df["cay"] = builder.cay

        # Step 2: enumerate all non-empty subsets of {c, a, y}
        rows = []
        r2_map: dict[frozenset, float] = {}

        for size in range(1, len(self._COMPONENTS) + 1):
            for subset in combinations(self._COMPONENTS, size):
                key = frozenset(subset)
                reg = PredictiveRegression(
                    df,
                    target_col=self.er_col,
                    predictor_cols=list(subset),
                    horizon=self.horizon,
                )
                reg.fit()
                r2 = reg.r_squared()
                r2_map[key] = r2
                t_stats = {col: reg.t_stat(col) for col in subset}
                rows.append(
                    {
                        "predictors": "+".join(sorted(subset)),
                        "r_squared": r2,
                        "n_obs": int(reg.result_.nobs),
                        "t_stats": t_stats,
                    }
                )

        # Also run the full CAY regression
        reg_cay = PredictiveRegression(
            df,
            target_col=self.er_col,
            predictor_cols=["cay"],
            horizon=self.horizon,
        )
        reg_cay.fit()
        rows.append(
            {
                "predictors": "cay",
                "r_squared": reg_cay.r_squared(),
                "n_obs": int(reg_cay.result_.nobs),
                "t_stats": {"cay": reg_cay.t_stat("cay")},
            }
        )

        self.results_ = pd.DataFrame(rows).sort_values("r_squared", ascending=False).reset_index(drop=True)

        # Step 3: Shapley-value decomposition
        self.shapley_ = self._shapley(r2_map)
        return self

    # ------------------------------------------------------------------
    def _shapley(self, r2_map: dict[frozenset, float]) -> pd.Series:
        """Compute Shapley values for R² attribution across c, a, y."""
        players = self._COMPONENTS
        n = len(players)
        shapley = {p: 0.0 for p in players}

        for i, player in enumerate(players):
            others = [p for p in players if p != player]
            for size in range(n):
                for subset in combinations(others, size):
                    s = frozenset(subset)
                    s_plus = frozenset(subset) | {player}
                    v_s = r2_map.get(s, 0.0)
                    v_s_plus = r2_map.get(s_plus, 0.0)
                    weight = (
                        math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
                    )
                    shapley[player] += weight * (v_s_plus - v_s)

        return pd.Series(shapley, name="shapley_r2").sort_values(ascending=False)

    # ------------------------------------------------------------------
    def summary(self) -> str:
        """Return a text summary of the decomposition."""
        if self.results_ is None:
            raise RuntimeError("Call fit() first.")
        lines = [
            "=== CAY Predictive Decomposition ===",
            "",
            "Predictive R² by predictor subset:",
            self.results_[["predictors", "r_squared", "n_obs"]].to_string(index=False),
            "",
            "Shapley-value R² attribution (c, a, y → er):",
        ]
        for name, val in self.shapley_.items():
            lines.append(f"  {name}: {val:.6f}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def plot_contributions(self, ax=None):
        """Bar chart of Shapley-value contributions."""
        import matplotlib.pyplot as plt

        if self.shapley_ is None:
            raise RuntimeError("Call fit() first.")
        fig, ax = (None, ax) if ax is not None else plt.subplots(figsize=(6, 4))
        self.shapley_.plot.bar(ax=ax, color=["#4C72B0", "#DD8452", "#55A868"])
        ax.set_title("Shapley-value R² attribution for CAY components → er")
        ax.set_ylabel("Shapley value (R²)")
        ax.set_xlabel("CAY component")
        ax.axhline(0, color="black", linewidth=0.8)
        if fig is not None:
            fig.tight_layout()
        return ax
