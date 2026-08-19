"""CAY construction via dynamic OLS (DOLS).

Lettau & Ludvigson (2001) estimate the long-run cointegrating relation

    c_t = const + β_a · a_t + β_y · y_t + cay_t

using Dynamic OLS (Stock & Watson, 1993) which augments the static OLS
regression with leads and lags of the first-differenced regressors to
correct for endogeneity and serial correlation.

The residual ``cay_t`` is the object of interest.
"""

from __future__ import annotations

import pandas as pd
from statsmodels.regression.linear_model import OLS
from statsmodels.tools import add_constant


class CayBuilder:
    """Estimate the CAY cointegrating residual.

    Parameters
    ----------
    df:
        DataFrame with columns ``c``, ``a``, ``y`` (log real per-capita
        series).  All series must share the same index.
    lags:
        Number of leads *and* lags of Δa, Δy to include in the DOLS
        augmentation.  Set to 0 for static OLS (useful for short samples
        or testing).

    Attributes (available after :meth:`fit`)
    ------------------------------------------
    cay : pd.Series
        Cointegrating residual (the CAY variable).
    coef_ : dict
        Estimated long-run coefficients ``{'const', 'beta_a', 'beta_y'}``.
    model_result_ :
        The underlying ``statsmodels`` OLS result object.
    """

    def __init__(self, df: pd.DataFrame, lags: int = 8):
        required = {"c", "a", "y"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame is missing columns: {missing}")
        if lags < 0:
            raise ValueError("lags must be nonnegative.")
        if not isinstance(df.index, pd.PeriodIndex) or not df.index.freqstr.startswith(
            "Q"
        ):
            raise ValueError("DataFrame must use a quarterly PeriodIndex.")
        if df.index.has_duplicates:
            raise ValueError("DataFrame index must contain unique quarters.")
        if df[["c", "a", "y"]].isna().any().any():
            raise ValueError(
                "DataFrame columns c, a, and y must not contain missing values."
            )
        if df.empty:
            raise ValueError("DataFrame must not be empty.")
        self._df = df[["c", "a", "y"]].copy()
        self.lags = lags
        self.cay: pd.Series | None = None
        self.coef_: dict | None = None
        self.model_result_ = None
        self.estimation_start_: pd.Period | None = None
        self.estimation_end_: pd.Period | None = None

    # ------------------------------------------------------------------
    def fit(self) -> "CayBuilder":
        """Estimate the long-run relation and compute CAY.

        Returns
        -------
        self
        """
        df = self._df.copy()

        # Build DOLS augmentation matrix
        da = df["a"].diff()
        dy = df["y"].diff()

        aug_cols: dict[str, pd.Series] = {}
        for k in range(-self.lags, self.lags + 1):
            aug_cols[f"da_lag{k}"] = da.shift(-k)
            aug_cols[f"dy_lag{k}"] = dy.shift(-k)

        X = pd.DataFrame({"a": df["a"], "y": df["y"], **aug_cols})
        X = add_constant(X)
        y = df["c"]

        # Align and drop rows with NaN (from differencing / shifting)
        combined = pd.concat([y, X], axis=1).dropna()
        if combined.empty:
            raise ValueError("No complete observations remain for DLS estimation.")
        y_clean = combined.iloc[:, 0]
        X_clean = combined.iloc[:, 1:]

        result = OLS(y_clean, X_clean).fit()
        self.model_result_ = result
        self.estimation_start_ = combined.index.min()
        self.estimation_end_ = combined.index.max()

        self.coef_ = {
            "const": result.params["const"],
            "beta_a": result.params["a"],
            "beta_y": result.params["y"],
        }

        # Paper convention: estimate the intercept, but do not subtract it.
        self.cay = (
            df["c"] - self.coef_["beta_a"] * df["a"] - self.coef_["beta_y"] * df["y"]
        ).rename("cay")
        return self

    # ------------------------------------------------------------------
    def summary(self) -> str:
        """Return a text summary of the cointegrating regression."""
        if self.model_result_ is None:
            raise RuntimeError("Call fit() first.")
        lines = [
            "=== CAY Cointegrating Regression (DOLS) ===",
            f"  const  : {self.coef_['const']:.6f}",
            f"  beta_a : {self.coef_['beta_a']:.6f}",
            f"  beta_y : {self.coef_['beta_y']:.6f}",
            f"  R²     : {self.model_result_.rsquared:.4f}",
            f"  N      : {int(self.model_result_.nobs)}",
        ]
        return "\n".join(lines)
