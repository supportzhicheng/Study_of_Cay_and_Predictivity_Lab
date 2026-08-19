"""Rolling / expanding-window predictivity monitor.

The monitor answers the live question:

    "Does CAY (or any other predictor) still have predictive power for
     excess stock returns in the most recent data?"

It runs a rolling OLS regression of excess returns on the predictor and
tracks:
- The rolling *t*-statistic (HAC) for the predictor.
- The rolling *R²*.
- A status flag: ``ACTIVE`` / ``WEAKENED`` / ``LOST``.

Status thresholds (configurable)
---------------------------------
- ``ACTIVE``   : |t| > t_active  (default 1.96 → ~5 % two-sided)
- ``WEAKENED`` : t_weak < |t| ≤ t_active  (default 1.28 → ~10 %)
- ``LOST``     : |t| ≤ t_weak
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from cay_lab.analysis.predictive_regression import PredictiveRegression


class RollingPredictivityMonitor:
    """Monitor rolling predictive power of a given predictor.

    Parameters
    ----------
    df:
        DataFrame containing the predictor and target columns.
    target_col:
        Column name of the series to be predicted (e.g. ``'er'``).
    predictor_col:
        Column name of the predictor (e.g. ``'cay'``).
    window:
        Number of observations in each rolling window.  Use ``None`` for
        an expanding window.
    horizon:
        Forecast horizon (periods ahead).
    t_active:
        |t| threshold above which the predictor is ``ACTIVE``.
    t_weak:
        |t| threshold below which the predictor is ``LOST``.

    Attributes (after :meth:`run`)
    --------------------------------
    rolling_results_ : pd.DataFrame
        One row per window end-date, columns:
        ``end_date``, ``t_stat``, ``r_squared``, ``n_obs``, ``status``.
    """

    STATUS_ACTIVE = "ACTIVE"
    STATUS_WEAKENED = "WEAKENED"
    STATUS_LOST = "LOST"

    def __init__(
        self,
        df: pd.DataFrame,
        target_col: str = "er",
        predictor_col: str = "cay",
        window: Optional[int] = 40,
        horizon: int = 1,
        t_active: float = 1.96,
        t_weak: float = 1.28,
    ):
        self._df = df[[predictor_col, target_col]].dropna().copy()
        self.target_col = target_col
        self.predictor_col = predictor_col
        self.window = window
        self.horizon = horizon
        self.t_active = t_active
        self.t_weak = t_weak
        self.rolling_results_: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    def run(self) -> "RollingPredictivityMonitor":
        """Execute the rolling / expanding window analysis."""
        df = self._df
        n = len(df)
        rows = []

        start_size = self.window if self.window is not None else 20

        for end in range(start_size, n + 1):
            if self.window is not None:
                start = end - self.window
            else:
                start = 0
            sub = df.iloc[start:end]

            reg = PredictiveRegression(
                sub,
                target_col=self.target_col,
                predictor_cols=[self.predictor_col],
                horizon=self.horizon,
            )
            try:
                reg.fit()
                t = reg.t_stat(self.predictor_col)
                r2 = reg.r_squared()
                nobs = int(reg.result_.nobs)
            except Exception:
                t, r2, nobs = np.nan, np.nan, 0

            status = self._classify(t)
            end_date = df.index[end - 1]
            rows.append(
                {
                    "end_date": end_date,
                    "t_stat": t,
                    "r_squared": r2,
                    "n_obs": nobs,
                    "status": status,
                }
            )

        self.rolling_results_ = pd.DataFrame(rows)
        return self

    # ------------------------------------------------------------------
    def _classify(self, t: float) -> str:
        if np.isnan(t):
            return self.STATUS_LOST
        abs_t = abs(t)
        if abs_t > self.t_active:
            return self.STATUS_ACTIVE
        elif abs_t > self.t_weak:
            return self.STATUS_WEAKENED
        else:
            return self.STATUS_LOST

    # ------------------------------------------------------------------
    def status(self) -> str:
        """Return the predictivity status based on the *latest* window."""
        if self.rolling_results_ is None:
            raise RuntimeError("Call run() first.")
        return str(self.rolling_results_["status"].iloc[-1])

    # ------------------------------------------------------------------
    def latest_summary(self) -> dict:
        """Return a dict summarising the latest window's statistics."""
        if self.rolling_results_ is None:
            raise RuntimeError("Call run() first.")
        row = self.rolling_results_.iloc[-1]
        return {
            "end_date": row["end_date"],
            "predictor": self.predictor_col,
            "t_stat": round(float(row["t_stat"]), 4),
            "r_squared": round(float(row["r_squared"]), 4),
            "n_obs": int(row["n_obs"]),
            "status": row["status"],
        }

    # ------------------------------------------------------------------
    def plot(self, ax=None):
        """Plot the rolling t-statistic and highlight status regions."""
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt

        if self.rolling_results_ is None:
            raise RuntimeError("Call run() first.")

        res = self.rolling_results_.copy()
        dates = res["end_date"].astype(str)

        if ax is not None:
            fig, ax_t, ax_r2 = None, ax, None
        else:
            fig, (ax_t, ax_r2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True)

        # --- t-statistic panel ---
        ax_t.plot(dates, res["t_stat"], color="#4C72B0", label="|t-stat|")
        ax_t.axhline(self.t_active, color="green", linestyle="--", label=f"t_active={self.t_active}")
        ax_t.axhline(-self.t_active, color="green", linestyle="--")
        ax_t.axhline(self.t_weak, color="orange", linestyle=":", label=f"t_weak={self.t_weak}")
        ax_t.axhline(-self.t_weak, color="orange", linestyle=":")
        ax_t.axhline(0, color="black", linewidth=0.8)
        ax_t.set_ylabel("HAC t-statistic")
        ax_t.set_title(
            f"Rolling Predictivity Monitor: {self.predictor_col} → {self.target_col}"
            + (f"  (window={self.window})" if self.window else "  (expanding)")
        )
        ax_t.legend(fontsize=8)
        step = max(1, len(dates) // 10)
        ax_t.set_xticks(range(0, len(dates), step))
        ax_t.set_xticklabels(dates.iloc[::step], rotation=45, ha="right", fontsize=7)

        # --- R² panel ---
        if ax_r2 is not None:
            ax_r2.fill_between(range(len(dates)), res["r_squared"], alpha=0.5, color="#DD8452")
            ax_r2.set_ylabel("R²")
            ax_r2.set_xlabel("Window end")
            ax_r2.set_xticks(range(0, len(dates), step))
            ax_r2.set_xticklabels(dates.iloc[::step], rotation=45, ha="right", fontsize=7)

        # Colour background by status
        colour_map = {
            self.STATUS_ACTIVE: "#d4f1d4",
            self.STATUS_WEAKENED: "#fff3cd",
            self.STATUS_LOST: "#f8d7da",
        }
        for i, row in res.iterrows():
            colour = colour_map.get(row["status"], "white")
            ax_t.axvspan(i, i + 1, alpha=0.25, color=colour, linewidth=0)

        patches = [
            mpatches.Patch(color=colour_map[s], label=s)
            for s in [self.STATUS_ACTIVE, self.STATUS_WEAKENED, self.STATUS_LOST]
        ]
        ax_t.legend(handles=patches + ax_t.get_lines()[:3], fontsize=8)

        if fig is not None:
            fig.tight_layout()
        return ax_t
