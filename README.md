# CAY Analysis Suite

## Overview

This repository independently replicates and updates Lettau and Ludvigson
(2001), "Consumption, Aggregate Wealth, and Expected Stock Returns."

The reported consumption-wealth trend deviation is constructed from log real
per-capita consumption (`c`), asset wealth (`a`), and labor income (`y`):

```
cay_t = c_t - β_a · a_t - β_y · y_t
```

The DLS regression estimates a constant, but the paper-convention CAY series
does not subtract it. CAY is a theory-motivated state variable, not a direct
measure of risk aversion or a trading signal.

The repository has two deliberately separate workstreams:

| Path | Description |
|---|---|
| `src/` | Core replication, updated analysis, acquisition, and reporting |
| `reports/` | Report contracts, LaTeX source, schemas, and generated artifacts |
| `notebooks/` | Inspection-only replication tour |
| `cay_lab/`, `cay_data/` | Optional pre-existing wealth-decomposition extension |
| `tests/` | Deterministic tests with fake service boundaries |

---

## Installation

```bash
mamba env create -f environment.yml
mamba activate cay
cp .env.example .env
```

Update an existing environment after the manifest changes with:

```bash
mamba env update -n cay -f environment.yml --prune
```

Keep `WRDS_USERNAME` and `BEA_API_KEY` in `.env`. Keep the WRDS password in
the user PostgreSQL password file. Raw licensed data, local reference files,
and generated artifacts are ignored by Git.

PDF report compilation additionally requires either Tectonic or a TeX
distribution that provides the `latexmk` and `pdflatex` command-line
executables. The unrelated PyPI package named `latexmk` does not provide these
executables. The included `environment.yml` installs Tectonic from conda-forge.

## Core replication workflow

Inspect configuration and available tasks:

```bash
python -m src.settings
doit list
```

The credentialed real-data build is:

```bash
python -m src.bootstrap_real_data --compile-report
```

Individual stages are also available:

```bash
python -m src.data.pull_author_cay
python -m src.data.pull_fred
python -m src.data.pull_bea
python -m src.data.pull_wrds
python -m src.data.import_local SOURCE_ID
python -m src.data.build_sources
python -m src.pipeline panel
python -m src.pipeline exhibits
python -m src.pipeline report
```

Live acquisition never fabricates fallback observations. Equivalent local
CSV, Parquet, XLSX, or XLS files may be supplied under `P10_INPUT_DIR`, but
they must satisfy the same normalized quarterly contracts.

## Verification

```bash
python -m pytest -q
ruff check .
ruff format --check src tests dodo.py settings.py \
   cay_lab/analysis/cay_builder.py cay_lab/data/__init__.py cay_lab/data/loader.py
git diff --check
```

The remaining sections document the optional decomposition extension.

## Repository structure

| Path | Purpose |
|---|---|
| `cay_data/` | Source and processed decomposition datasets used in this project |
| `cay_lab/data/` | Data loading, cleaning, and predictivity-dataset preparation |
| `cay_lab/analysis/` | CAY construction and predictive regression logic |
| `cay_lab/monitor/` | Rolling/expanding predictivity monitor |
| `cay_lab/dodo.py` | Automated `doit` tasks (model runs + chartbook export) |
| `tests/` | Unit tests |

---

## Quickstart

### 1 – Construct CAY

```python
from cay_lab.analysis.cay_builder import CayBuilder

builder = CayBuilder(df)          # df has columns: c, a, y (log-levels)
builder.fit()
print(builder.cay)                # pd.Series of cay residuals
print(builder.coef_)              # {'beta_a': ..., 'beta_y': ..., 'const': ...}
```

### 2 – Decompose CAY

```python
from cay_lab.analysis.decomposition import CayDecomposer

decomp = CayDecomposer(df, excess_returns_col='er')
decomp.fit()
print(decomp.summary())           # contribution of each component
decomp.plot_contributions()
```

### 3 – Rolling Predictivity Monitor

```python
from cay_lab.monitor.rolling_monitor import RollingPredictivityMonitor

monitor = RollingPredictivityMonitor(df, target_col='er', predictor_col='cay',
                                     window=40)
monitor.run()
print(monitor.status())           # 'ACTIVE' / 'WEAKENED' / 'LOST'
monitor.plot()
```

---

## End-to-end workflow (recommended)

If you are new to the repo, follow this exact sequence:

1. **Install dependencies**
   ```bash
   mamba env create -f environment.yml
   mamba activate cay
   ```
2. **(Optional) Rebuild decomposition data files**
   ```bash
   /usr/bin/python3 cay_data/build_components_from_s14.py
   /usr/bin/python3 cay_data/build_extension_data.py
   ```
3. **Run tests**
   ```bash
   pytest -q
   ```
4. **Generate predictivity outputs + chartbook**
   ```bash
   doit -f cay_lab/dodo.py chartbook \
     --dataset wealth_groups \
     --train-periods 40 \
     --prediction-window 1 \
     --target-component financial
   ```
5. **Read outputs**
   - `cay_lab/output/subcay_predictivity_prepared.csv`
   - `cay_lab/output/subcay_predictivity_rolling.csv`
   - `cay_lab/output/chartbook_subcay_predictivity.pdf`

---

## Data Guide (for decomposition extension)

All extension data lives in `cay_data/`.

### What each dataset means

| File | What it contains | Frequency | Unit |
|---|---|---|---|
| `cay_data/cay_components_households_q.csv` | Household-only asset-class decomposition (`housing`, `financial`, `liquid`) | Quarterly | Million USD |
| `cay_data/cay_components_hnpo_q.csv` | Households + nonprofits asset-class decomposition (`housing`, `financial`, `liquid`) | Quarterly | Million USD |
| `cay_data/cay_components_wealth_groups_q.csv` | Wealth-group decomposition (`top10`, `middle40`, `bottom50`) with asset classes | Quarterly | Million USD |
| `cay_data/cay_components_region_ca_il_tx_q_proxy.csv` | Regional decomposition proxy for California, Illinois, Texas with asset-class shares and scaled levels | Quarterly | Shares + million-USD scaled proxy |
| `cay_data/series_metadata.csv` | Exact Z.1 series codes used for asset-class construction | — | — |
| `cay_data/region_proxy_method.csv` | Exact construction rules for the regional proxy | — | — |
| `cay_data/data_availability.csv` | Summary of what is direct data vs proxy data | — | — |

### Data interpretation notes (important)

1. **Asset-type decomposition is direct** from Federal Reserve Z.1 tables.
2. **Wealth-level decomposition is direct** from DFA (Distributional Financial Accounts):
   - `top10 = TopPt1 + RemainingTop1 + Next9`
   - `middle40 = Next40`
   - `bottom50 = Bottom50`
3. **Region decomposition is a proxy**, not directly reported regional balance-sheet levels in Z.1:
   - Housing share uses state HPI + population normalization.
   - Financial share uses state estimated personal-income share (`PCPI × population`).
   - Liquid share currently follows the financial share (income-based fallback), with optional FDIC override support.

### Coverage notes

- In `cay_components_households_q.csv`, `financial` and `liquid` start later than `housing` (first non-missing quarter is **1987Q4** for both), while housing starts in **1945Q4**.
- `cay_components_hnpo_q.csv` has all three components from **1945Q4** onward, so it is the best long-span base series.
- Wealth-group and region files are aligned to the extension period beginning in **1989Q3**.

### Rebuild the extension data

From repository root:

```bash
/usr/bin/python3 cay_data/build_components_from_s14.py
/usr/bin/python3 cay_data/build_extension_data.py
```

Raw downloaded inputs are stored in `cay_data/raw/` for reproducibility.

---

## Automated predictivity chartbook (doit)

We provide a `doit` pipeline at `cay_lab/dodo.py` to run rolling predictivity
tests on sub-cay variables and generate a chartbook.

### Run

```bash
doit -f cay_lab/dodo.py chartbook \
  --dataset wealth_groups \
  --train-periods 40 \
  --prediction-window 1 \
  --target-component financial
```

### Key options

- `--dataset`: `households`, `households_and_nonprofits`, `wealth_groups`, `region_proxy`
- `--train-periods`: rolling training sample length in quarters
- `--prediction-window`: forecast horizon in quarters
- `--target-component`: `housing`, `financial`, or `liquid`
- `--output-dir`: output folder (default: `cay_lab/output`)
- `--min-history-periods`: minimum history for the expanding-mean sub-cay transform

### Outputs

- `cay_lab/output/subcay_predictivity_prepared.csv`
- `cay_lab/output/subcay_predictivity_rolling.csv`
- `cay_lab/output/chartbook_subcay_predictivity.pdf`

---

## Use from Python directly

```python
from cay_lab.data import prepare_predictivity_dataset

df = prepare_predictivity_dataset(
    dataset="wealth_groups",
    train_periods=40,
    prediction_window=1,
    target_component="financial",
)
print(df.head())
```

This returns a cleaned modeling table with:
- `segment` (wealth group or region),
- `sub_cay_housing`, `sub_cay_financial`, `sub_cay_liquid`,
- `target_future_growth`.

---

## Background

Lettau, M. and Ludvigson, S. (2001). *Consumption, Aggregate Wealth, and Expected
Stock Returns*. **Journal of Finance**, 56(3), 815–849.