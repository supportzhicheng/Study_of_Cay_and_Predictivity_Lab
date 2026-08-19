"""Predictive regression utilities.

Provides a thin wrapper around OLS for single-period-ahead return
prediction regressions, with Newey-West standard errors.
"""

from __future__ import annotations

import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant


class PredictiveRegression:
    """Run a one-period-ahead predictive OLS regression.

    Regresses ``target_col[t+h]`` on ``predictor_cols[t]``.

    Parameters
    ----------
    df:
        DataFrame containing the target and predictor series.
    target_col:
        Name of the column to predict.
    predictor_cols:
        List of predictor column names.
    horizon:
        Forecast horizon (default 1 period ahead).
    max_lags:
        Maximum lags for Newey-West HAC standard errors.
        If *None*, uses ``int(4*(n/100)^(2/9))`` (the common default).

    Attributes (after :meth:`fit`)
    --------------------------------
    result_ :
        statsmodels OLS result with HAC standard errors.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        target_col: str,
        predictor_cols: list[str],
        horizon: int = 1,
        max_lags: int | None = None,
    ):
        self._df = df.copy()
        self.target_col = target_col
        self.predictor_cols = predictor_cols
        self.horizon = horizon
        self.max_lags = max_lags
        self.result_ = None

    def fit(self) -> "PredictiveRegression":
        df = self._df
        y = df[self.target_col].shift(-self.horizon)
        X = df[self.predictor_cols]
        X = add_constant(X)
        combined = pd.concat([y, X], axis=1).dropna()
        y_c = combined.iloc[:, 0]
        X_c = combined.iloc[:, 1:]
        n = len(y_c)
        lags = self.max_lags if self.max_lags is not None else int(4 * (n / 100) ** (2 / 9))
        self.result_ = OLS(y_c, X_c).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        return self

    def t_stat(self, col: str) -> float:
        """Return the HAC t-statistic for *col*."""
        if self.result_ is None:
            raise RuntimeError("Call fit() first.")
        return float(self.result_.tvalues[col])

    def r_squared(self) -> float:
        if self.result_ is None:
            raise RuntimeError("Call fit() first.")
        return float(self.result_.rsquared)

    def summary(self) -> str:
        if self.result_ is None:
            raise RuntimeError("Call fit() first.")
        lines = [
            f"=== Predictive Regression: {self.target_col}[t+{self.horizon}] ===",
        ]
        for col in self.predictor_cols:
            coef = self.result_.params[col]
            tval = self.result_.tvalues[col]
            pval = self.result_.pvalues[col]
            lines.append(f"  {col:20s}: coef={coef:+.4f}  t={tval:+.3f}  p={pval:.4f}")
        lines.append(f"  R²: {self.result_.rsquared:.4f}   N: {int(self.result_.nobs)}")
        return "\n".join(lines)
