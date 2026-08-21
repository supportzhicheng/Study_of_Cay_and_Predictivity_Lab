# Unified Workflow, Data, Replication, and Report Plan

**Status:** Implemented through Phases 0--5; exact Section 9 baseline bundle remains externally blocked

Implementation commits:

1. `7a63764` -- stabilize migration baselines and tests.
2. `5eb220e` -- fix historical replication methods.
3. `47f85fc` -- unify extension code and workflow.
4. `980e19e` -- unify extension data contracts.
5. `427865c` -- rebuild publication report artifacts.

The regional baseline and complete report workflow pass. Exact Section 9
baseline reproduction still requires the pinned QQQ bytes documented in
`docs/BASELINE_BUNDLE_STATUS.md`; baseline mode rejects the available revised
cache rather than silently substituting it.

## 1. Goal and Decisions

Build the full report through one root workflow, one code tree, and one ignored
data root. Preserve the current empirical products while removing duplicate
code, hidden inputs, checked-in data, and broken report rendering.

Decisions:

1. Root `dodo.py` is the only workflow entry point.
2. `src` is the project namespace. Move extension code to `src/extension`; do
   not create an installable `cay_lab` library.
3. Use `environment.yml` only. Remove `pyproject.toml` and editable-install
   instructions.
4. Store all raw, normalized, and processed data under `_data`; store generated
   analysis under `_output` and report artifacts under `reports`.
5. Keep source metadata, hashes, schemas, and synthetic fixtures in Git. Do not
   track provider bytes or generated datasets.
6. Keep empirical-method changes separate from structural moves.
7. Do not change paper targets or widen tolerances.

## 2. Verified Current State

- Root `dodo.py` has 16 tasks; `cay_lab/dodo.py` has 5 overlapping tasks and
  also contains analysis and chartbook code.
- Implementation is split across 37 Python files in `src`, 14 in `cay_lab`, and
  two builders in `cay_data`.
- Status classification, rolling predictivity, segment tests, and chartbook
  rendering have duplicate implementations.
- `pyproject.toml` points to a nonexistent `src/cay_lab` package.
- `cay_data` contains 29 tracked files totaling 1,688,055 bytes and mixes raw
  snapshots, generated datasets, metadata, and scripts.
- Root `doit compile_report` works with existing caches, but `build_panel` does
  not depend on `normalize_pulled_sources`; an empty `_data` build is incomplete.
- The regional report reads both extension data and
  `_data/processed/core_quarterly.parquet`. It currently degrades silently when
  the core panel is missing.
- Section 9 reads an undeclared QQQ cache or falls back to mutable Stooq/Yahoo
  downloads.
- Extension tests read real `cay_data` files instead of generated fixtures.
- The latest full test record has 159 tests and two failures: a stale optional
  WRDS-password fixture and a concurrency expectation not implemented by the
  sequential bootstrap.

## 3. Target Structure and Workflow

```text
Study_of_Cay_and_Predictivity_Lab/
|-- .env.example
|-- .gitignore
|-- README.md
|-- environment.yml
|-- chartbook.toml
|-- ruff.toml
|-- dodo.py
|-- settings.py
|-- src/
|   |-- settings.py
|   |-- pipeline.py
|   |-- data/
|   |   |-- core acquisition and normalization
|   |   `-- extension acquisition and preparation
|   |-- analysis/
|   |   |-- cay_builder.py
|   |   `-- core analysis
|   |-- reporting/
|   `-- extension/
|       |-- loader.py
|       |-- decomposition.py
|       |-- predictive_regression.py
|       |-- predictivity.py
|       |-- rolling_monitor.py
|       |-- pipeline.py
|       |-- reporting.py
|       `-- chartbook.py
|-- tests/
|-- config/
|-- docs/
|   `-- WORKFLOW_CONVERGENCE_PLAN.md
|-- notebooks/
|-- reports/
|   |-- build/
|   |   `-- main.pdf                 # ignored final report
|   |-- tables/appendix/
|   |-- figures/
|   `-- paper/generated/
|-- _data/                         # ignored
|   |-- raw/core/
|   |-- raw/extension/
|   |-- normalized/core/
|   |-- normalized/extension/
|   |-- processed/core_quarterly.parquet
|   `-- processed/extension/
`-- _output/extension/             # ignored
```

`.env` remains a local ignored secrets file; `.env.example` is the tracked
template. `.git/` is repository metadata and is not part of the managed project
layout. `pyproject.toml` is intentionally absent because this repository is not
being packaged; `environment.yml` is the sole environment definition.

Root task graph:

```text
config
|-- core_acquire -> core_prepare -> build_panel -> generate_exhibits
`-- extension_acquire -> extension_prepare -> extension_analyze
                                      |-- extension_region_report
                                      `-- extension_section9_chartbook

build_panel ---------------------------> extension_region_report

generate_exhibits + extension_region_report + extension_section9_chartbook
    -> compile_report
```

Rules:

- Every generated target has one owner and complete file/task dependencies.
- `extension_region_report` depends on `build_panel`; missing core data is an
  error.
- Section 9 may run in parallel with core exhibits; `compile_report` joins the
  branches.
- `doit compile_report` works from an empty `_data` root after credentials or a
  verified local source bundle are supplied.
- A second report build is a no-op.

## 4. Data Contract

Use these paths:

```text
_data/raw/extension/
_data/raw/extension/market/
_data/normalized/extension/
_data/processed/extension/
_output/extension/
reports/paper/generated/extension_report.tex
```

Required extension inputs:

```text
Federal Reserve Z.1 S14.b
Federal Reserve Z.1 S1M.b
Federal Reserve DFA ZIP (extract dfa-networth-levels-detail.csv only)
FRED CASTHPI, ILSTHPI, TXSTHPI, USSTHPI
FRED CAPCPI, ILPCPI, TXPCPI
FRED CAPOP, ILPOP, TXPOP
QQQ daily adjusted-close prices for the Section 9 sample
```

FDIC remains disabled and requires no source file. Verify every regional row
uses `income_share_fallback`.

After the Phase 3 baseline gate, do not move, copy, or track files with no
runtime consumer: supplemental OECD/S1M-e Z.1 extracts, DFA general-level files
and dictionaries, and `data_availability.csv`.

Acquisition modes:

- `baseline`: import or download hash-verified core and extension sources and
  reproduce the recorded report. Resolve local extension bundles from
  `EXTENSION_INPUT_DIR`.
- `latest`: acquire current BEA, FRED, Shiller, WRDS, Federal Reserve, and market
  data; write a new manifest and never overwrite baseline hashes.

Live acquisition can populate `_data`, but revised providers cannot guarantee
byte-identical results. Exact reproduction requires the pinned source bundle.
Document credentials and local bundles under README `Data Sources and Setup`;
they are prerequisites, not hidden files.

`config/extension_sources.yml` records provider, source ID/query, vintage,
coverage, units, cache path, acquisition mode, and SHA-256. QQQ is a declared
source; chartbook rendering never performs hidden network fallback.

Current QQQ cache reference:

```text
rows: 814
coverage: 2023-01-03 through 2026-04-01
SHA-256: ecbcf48746b1167b502d06fd07022f3f2ff7eff69fb89c4d4b08a8853c802bbb
```

Extension tests use synthetic temporary inputs. Section 8/9 report inputs are
required task outputs, not `\IfFileExists` fallbacks.

## 5. Output Baselines

Record these in `tests/fixtures/migration_baseline.json` before moving code or
paths.

```text
Regional extension
prepared rows: 414
rolling rows: 294
segments: California, Illinois, Texas
status: ACTIVE 207, WEAKENED 46, LOST 41
prepared SHA-256: 628aa0fc06e7daa9fd20560343dcd824390d66be8f4f611c55a7acf79b586c48
rolling SHA-256: 802f7baec074b2f0ebdb9d1459d5824234970f76472f078eb1d3253433aa1bae

Section 9 example
prepared rows: 30
rolling rows: 6
segments: bottom50, middle40, top10
prepared SHA-256: e83e66a794ee34d8cb0709dcc6cc66719734c12fae2e90f8e74ba212561ba61d
rolling SHA-256: 7bc1dff59f855082093ca338c3d3b5748d78b1e44805492e02a4a930c751bbae
```

Also record the core panel, report exhibit inventory, audit values, and current
regional/Section 9 chartbook page counts. Compare PDF content semantically;
PDF metadata need not match bytes.

## 6. Historical Replication Fix

### Diagnosis

The current pipeline selects bill and term-spread candidates by minimizing
Table III target error, then audits against those targets. Replace that circular
selection with the source-defined historical contract:

```text
risk-free return: CRSP 30-day Treasury bill (t30ret)
term spread: 10-year Treasury yield minus 3-month Treasury yield
CRSP market return: vwretd
quarterly return: sum monthly log1p returns
relative bill rate: current bill return minus the prior four-quarter mean
HAC lags: max(1, horizon - 1)
```

Two implementation choices caused the three failures:

1. RREL includes the current quarter in its own four-quarter benchmark.
2. One-quarter regressions use an unrelated automatic four-lag HAC bandwidth.

Verified corrections:

```python
relative_bill_rate = (
    nominal_rate - nominal_rate.shift(1).rolling(4, min_periods=4).mean()
)


def newey_west_lags(observations: int, horizon: int) -> int:
    return max(1, horizon - 1)
```

Results:

```text
RREL fix only: 28 strict, 9 revised-vintage, 2 failed
RREL + HAC fix: 24 strict, 15 revised-vintage, 0 failed
```

Key corrected values:

| Metric | Actual | Target | Status |
|---|---:|---:|---|
| Table II RREL/cay correlation | -0.1823 | -0.23 | revised-vintage |
| Table III row 4 cay t-statistic | 3.9969 | 4.754 | revised-vintage |
| Table III row 8 cay t-statistic | 4.0761 | 4.583 | revised-vintage |
| Table III row 13 cay coefficient | 1.6244 | 1.906 | revised-vintage |
| Table III row 13 cay t-statistic | 2.8320 | 3.197 | strict |
| Table III row 13 term coefficient | -0.0710 | -0.082 | strict |
| Table III row 13 adjusted R-squared | 0.1032 | 0.10 | strict |

Row 13 starts in 1953Q2 with 181 observations. Every Table VI check remains
strict or revised-vintage; its lag set is 1, 1, 2, 3, 7, 11, 15, and 23 for
horizons 1, 2, 3, 4, 8, 12, 16, and 24.

Sensitivity checks ruled out `vwretx`, `t90ret`, return arithmetic, predictor
timing, and CAY calibration as fixes. Store all sensitivity results, source
definitions, and ruling-out evidence in
`reports/build/table_iii_source_diagnostics.json`.

Required tests:

- RREL excludes the current quarter.
- Historical primary columns use `bill_30d` and `term_10y_3m`.
- Table III uses one HAC lag.
- Table VI uses `max(1, h-1)`.
- Row 13 starts in 1953Q2 with 181 observations.
- All 39 audit checks are strict or revised-vintage passes.

## 7. Report Contract

### Current Defects

| PDF table | Artifact | Defect |
|---:|---|---|
| 1 | `table_ii_replication` | 45 structural `NaN` cells |
| 2 | `table_iii_replication` | 40 term rows for 13 models |
| 3 | `table_vi_replication` | 128 term rows for 48 models; oversized float |
| 4 | `table_ii_updated` | 45 structural `NaN` cells |
| 5 | `table_iii_updated` | 40 term rows for 13 models |
| 6 | `table_vi_updated` | 128 term rows for 48 models; oversized float |
| 7 | `table_s1_core_data_summary` | 220 structural `NaN` cells |

Root causes:

- Raw tidy frames are passed directly to `DataFrame.to_latex`.
- Incompatible panels are concatenated into union schemas.
- Regression output has one row per coefficient term, not per model.
- Oversized floats cross section boundaries.
- Caption validation prompts are emitted as display text; data vintage repeats.
- Sections 3--5 have subsection headings but no interpretation paragraphs.

### Publication Tables

Keep analysis functions and statistical methods unchanged. Add table-specific
adapters under `src/reporting/tables.py`; report tables never serialize raw
analysis frames.
Use explicit blank publication cells and reject unexpected numerical missing
values.

- **Table 1:** five-row historical moments panel plus lower-triangular
  correlation panel.
- **Table 2:** all 13 historical one-quarter models exactly once across
  return-definition, predictor-comparison, and full-control panels. Predictor
  cells contain coefficient and parenthesized HAC t-statistic.
- **Table 3:** two historical panels (consumption growth and excess returns),
  eight horizon rows each. Full 48-model results go to appendix longtables/CSV.
- **Table 4:** historical-versus-updated moments and correlations. Do not compare
  raw historical and updated `cay` means; additive normalization differs.
- **Table 5:** rows 2, 4, 6, 8, and 13 compare historical and updated `cay`
  estimates. Full 13-model updated output goes to the appendix/CSV.
- **Table 6:** historical-versus-updated long-horizon panels. Full 48-model
  updated output goes to the appendix/CSV.
- **Table 7:** separate coverage, historical summary, and updated summary panels.
- **Table 8:** status totals and non-strict checks in the main report; all 39
  checks remain in appendix/CSV.

Write appendix detail under `reports/tables/appendix/`, generate
`reports/paper/generated/appendix_tables.tex`, and include it once from
`appendix.tex` using `longtable`, not floating tables.

Separate machine-readable frames from rendered TeX. Store incompatible panels
as separate CSV files. Derive artifacts from `report_contract.yml`; remove the
hard-coded 32-artifact count.

### Evidence Paragraphs and Captions

Add `src/reporting/findings.py::write_empirical_findings`. It writes
`reports/paper/generated/empirical_findings.tex` with these macros:

```text
HistoricalSummaryFinding
HistoricalFigureFinding
HistoricalShortHorizonFinding
HistoricalLongHorizonFinding
UpdatedSummaryFinding
UpdatedFigureFinding
UpdatedShortHorizonFinding
UpdatedLongHorizonFinding
DataCoverageFinding
DataAnatomyFinding
```

Include the generated file once from `main.tex`. Sections 3--5 invoke the
matching macro immediately after each subsection heading and before the exhibit.
Each paragraph states what was tested, what the generated evidence says, and why
it matters.

Macro order is explicit: Section 3 uses the four `Historical*` macros; Section
4 uses the four `Updated*` macros; Section 5 uses `DataCoverageFinding` and
`DataAnatomyFinding`.

Make `report_contract.yml` the sole exhibit registry and remove
`reports/captions.yml`. Each entry owns title, label, section, role, paths,
sample rule, benchmark citation, provider citations, source IDs, and source
note. Caption rendering never emits validation prompts or instructional text.
It emits data vintage once and requires explicit display notes/takeaways.

Add `placeins` and `\FloatBarrier` before each report section. Main tables fit
one page and `\textwidth`; appendix detail uses `longtable`.

### Exhibit Registry

Source bundles:

- **H:** LL author historical macro inputs; Shiller S&P/dividend/earnings/CPI;
  CRSP `vwretd`/`t30ret`; FRED rates/spreads and FRED/NBER recessions as used.
- **U:** BEA consumption/labor income; Federal Reserve/FRED wealth and rates;
  Shiller, CRSP, and FRED/NBER current-vintage inputs.
- **R:** Federal Reserve Z.1 HNPO wealth scaled by FRED state
  HPI/income/population shares, plus required U core variables.
- **W:** Federal Reserve DFA wealth-group detail plus pinned QQQ adjusted-close
  prices; provider recorded in `extension_sources.yml`.
- **A:** Fixed LL targets, author-posted `cay`, and generated audit values.

Tables:

| # | Artifact | Title | Label | Benchmark | Source |
|---:|---|---|---|---|---|
| 1 | `table_ii_replication` | Historical Summary Statistics and Correlations | `tab:historical_summary` | LL Table II | H |
| 2 | `table_iii_replication` | Historical One-Quarter Return Forecasts | `tab:historical_one_quarter` | LL Table III | H |
| 3 | `table_vi_replication` | Historical Long-Horizon CAY Regressions | `tab:historical_long_horizon` | LL Table VI | H |
| 4 | `table_ii_updated` | Updated Summary Statistics: Historical Comparison | `tab:updated_summary` | follows LL Table II | U |
| 5 | `table_iii_updated` | Updated One-Quarter CAY Forecasts: Historical Comparison | `tab:updated_one_quarter` | follows LL Table III | U |
| 6 | `table_vi_updated` | Updated Long-Horizon CAY Forecasts: Historical Comparison | `tab:updated_long_horizon` | follows LL Table VI | U |
| 7 | `table_s1_core_data_summary` | Core Data Coverage and Diagnostics | `tab:data_diagnostics` | none | U |
| 8 | `table_r1_replication_audit` | Historical Replication Audit | `tab:replication_audit` | LL Tables II/III/VI and author-posted `cay` | A |
| 9 | `table_ii_extension_cay_r` | Regional-Proxy CAY Summary Statistics | `tab:regional_summary` | follows LL Table II | R |
| 10 | `table_iii_extension_cay_r` | Regional-Proxy One-Quarter Return Forecasts | `tab:regional_one_quarter` | follows LL Table III | R |
| 11 | `table_vi_extension_cay_r` | Regional-Proxy Long-Horizon Forecasts | `tab:regional_long_horizon` | follows LL Table VI | R |

Figures:

| # | Artifact/segment | Title | Label | Benchmark | Source |
|---:|---|---|---|---|---|
| 1 | `figure_1_replication` | Historical CAY and Excess Returns | `fig:historical_cay_returns` | LL Figure 1 | H |
| 2 | `figure_1_updated` | Updated CAY and Excess Returns | `fig:updated_cay_returns` | follows LL Figure 1 | U |
| 3 | `figure_s1_data_anatomy` | Consumption, Income, and Wealth: Levels and Growth | `fig:data_anatomy` | none | U |
| 4 | `figure_1_extension_cay_r` | Regional-Proxy CAY and Excess Returns | `fig:regional_cay_returns` | follows LL Figure 1 | R |
| 5 | `bottom50` | Bottom 50%: Two-Quarter QQQ Forecast Diagnostics | `fig:section9_bottom50` | none | W |
| 6 | `middle40` | Middle 40%: Two-Quarter QQQ Forecast Diagnostics | `fig:section9_middle40` | none | W |
| 7 | `top10` | Top 10%: Two-Quarter QQQ Forecast Diagnostics | `fig:section9_top10` | none | W |

Historical exhibits are authors' calculations benchmarked to LL, not numbers
copied from the paper. Updated/regional captions say the specification follows
LL and identify actual providers.

Regional Tables 9--11 become numbered table environments. A generated Section 9
manifest maps page number to segment, sample, target, source hash, and label;
Figures 5--7 never assume page order.

Registry citation keys must exist in `references.bib`; source IDs must exist in
the core/extension source manifests. `artifact_manifest.json` records each
exhibit's source IDs and resolved input hashes. Validation rejects defaults,
unknown sources, or declared sources absent from task/file dependencies.

## 8. Execution Plan

### Phase 0: Protect State and Stabilize Tests

1. Preserve current modifications under `cay_data/raw` and the untracked QQQ
   cache.
2. Record core, regional, Section 9, and report baselines.
3. Split regional and Section 9 fixture sections.
4. Fix the optional WRDS-password test and replace the stale concurrency test
   with sequential order, cache, logging, and failure-propagation tests.
5. Run the full suite in the declared `cay` environment.

**Gate:** no failing tests; small baseline fixtures are committed.

### Phase 1: Fix Historical Methods

1. Fix the historical convention to `bill_30d` and `term_10y_3m`; retain other
   candidates as labeled robustness results.
2. Apply the RREL and HAC formulas in Section 6.
3. Add lineage/sensitivity diagnostics and regression tests.
4. Regenerate Table R1; document exact methods in report methodology, captions,
  and the generated diagnostic JSON.

**Gate:** 24 strict, 15 revised-vintage, 0 failed; all 39 targets/tolerances are
unchanged.

### Phase 2: Keep One Workflow and Code Tree

1. Move reusable chartbook analysis out of `cay_lab/dodo.py`; root tasks call
   extension modules directly. Delete the legacy task file.
2. Consolidate predictivity/status/chartbook implementations.
3. Remove `test_main.pdf`, per-run Jupyter kernel installation, and duplicate
   bootstrap orchestration.
4. Fix core task dependencies and target ownership.
5. Move `cay_lab/analysis/cay_builder.py` to `src/analysis/cay_builder.py`; move
  other extension modules to `src/extension`; update imports, task
  dependencies, report inputs, notebooks, and tests.
6. Merge extension paths into `src.settings.Settings`.
7. Delete `cay_lab`, `pyproject.toml`, packaging tests, editable-install docs,
   and compatibility shims unless an actual external consumer is found.

**Gate:** root `doit list` is the only task surface; no import starts with
`cay_lab`; tests and output baselines pass; second report build is a no-op.

### Phase 3: Unify and Untrack Data

1. Move extension builders to `src/data` and parameterize all paths.
2. Implement `extension_acquire`, `extension_prepare`, `extension_analyze`,
   `extension_region_report`, and `extension_section9_chartbook`.
3. Implement baseline/latest acquisition modes and QQQ source handling.
4. Make regional report depend on the core panel; replace real-data tests with
   synthetic fixtures; remove silent report fallbacks.
5. Rebuild from an empty temporary `_data` root with the baseline bundle.
6. Add ignored data/output paths, remove tracked provider/generated bytes, and
   delete `cay_data` only after the clean-room gate passes.

**Gate:** clean baseline rebuild matches the Section 5 regional/Section 9
hashes; `git ls-files` contains no provider/generated data; no test reads
deleted fixtures.

### Phase 4: Rebuild Report Presentation

1. Add table-specific publication adapters and appendix longtables.
2. Add generated evidence paragraphs and concise captions.
3. Consolidate exhibit metadata into `report_contract.yml`; add all core,
   regional, and Section 9 entries from Section 7.
4. Add source IDs/hashes, citation validation, segment page manifest, and
   semantic labels.
5. Add float barriers and update the artifact contract.
6. Add report/PDF tests.

**Gate:** Sections 3--5 form a connected argument; Tables 1--7 contain no
structural nulls or duplicate term rows; Tables 9--11 are numbered; all 18
labels/sources validate; exhibit order, audit values, regional outputs, and
Section 9 outputs pass.

### Phase 5: Documentation and Final Verification

1. Rewrite README for one environment, one root workflow, baseline/latest data
   modes, credentials, and output locations.
2. Remove obsolete `cay_lab`, `cay_data`, editable-install, and legacy task
   instructions.
3. Replace absolute artifact-manifest paths with repository-relative paths.
4. Run the full verification matrix below.

## 9. Verification

```bash
python -m pytest -q
ruff check .
ruff format --check .
git diff --check
doit list
doit compile_report
doit compile_report
```

Required report checks:

- no core table TeX or extracted PDF text contains literal `NaN`;
- Table 2 contains model IDs 1--13 once; Table 5 contains 2/4/6/8/13 once;
- populated regression cells match source coefficients/t-statistics;
- Tables 3/6 contain two panels and eight horizons; appendix contains all 48
  historical and 48 updated model keys;
- no main table prints constants, raw p-values, or repeated metadata;
- every Section 3--5 subsection has one generated evidence paragraph;
- captions contain no instructions, duplicate vintage, raw labels, or default
  source text;
- Tables 1--3 precede Section 4; Tables 4--6 precede Section 5; Table 7 is in
  Section 5;
- no core report `Float too large` or overfull-table warning;
- 11 tables and 7 figures have unique labels, benchmarks, provider sources,
  valid citations, source IDs, and input hashes;
- Tables 9--11 are numbered; Figure 4 and Figures 5--7 have source-complete,
  segment-correct captions;
- final `main.log` has no unresolved citation/reference or duplicate label;
- the audit remains 24 strict, 15 revised-vintage, 0 failed;
- regional and Section 9 baselines match;
- the second `doit compile_report` performs no actions or file writes; verify
  task output and unchanged file hashes.

## 10. Completion Criteria

- One code tree: `src`.
- One workflow: root `dodo.py`.
- One environment definition: `environment.yml`.
- No `cay_lab`, `cay_data`, or `pyproject.toml`.
- No provider or generated data tracked by Git.
- Empty `_data` rebuild works with a verified source bundle.
- All tests, lint, report, source, and clean-room checks pass.
- Historical audit: 24 strict, 15 revised-vintage, 0 failed.
- Sections 3--5 contain concise generated interpretation.
- Report tables contain no structural nulls, duplicate term rows, or misplaced
  floats.
