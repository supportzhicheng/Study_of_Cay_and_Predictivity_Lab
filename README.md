# CAY Replication and Predictivity Lab

This repository independently replicates and updates Lettau and Ludvigson
(2001), then extends the analysis with regional and wealth-group predictivity
workflows. The project has one Python namespace (`src`), one task runner
(root `dodo.py`), one environment definition, and one ignored data root.

## Environment

```bash
mamba env create -f environment.yml
mamba activate cay
cp .env.example .env
```

Update an existing environment with:

```bash
mamba env update -n cay -f environment.yml --prune
```

Do not install the unrelated PyPI package named `latexmk`. The environment
includes Tectonic for report compilation.

## Credentials and Source Bundles

Set `WRDS_USERNAME` for WRDS acquisition.
Set `BEA_API_KEY` for BEA acquisition.
Secrets and provider data are ignored by Git.

Extension acquisition has two modes:

- `latest` (default): downloads current DFA, FRED, and QQQ data and uses local
  Z.1 inputs.
- `baseline`: imports every hash-verified source from `EXTENSION_INPUT_DIR` and
  rejects revised bytes.

Configure the mode in `.env`:

```text
EXTENSION_ACQUISITION_MODE=baseline
EXTENSION_INPUT_DIR=/absolute/path/to/pinned-source-bundle
```

The required files, coverage, units, cache paths, and SHA-256 values are listed
in `config/extension_sources.yml`.

## Workflow

Inspect the sole task surface:

```bash
doit list
```

Build the complete report:

```bash
doit compile_report
```

The root graph includes:

```text
config
|-- core acquisition/preparation -> build_panel -> generate_exhibits
`-- extension_acquire -> extension_prepare -> extension_analyze
                                      |-- extension_region_report
                                      `-- extension_section9_chartbook

generate_exhibits + extension_region_report + extension_section9_chartbook
    -> compile_report
```

Other useful tasks:

```bash
doit bootstrap_real_data
doit run_notebook
doit run_tests
doit extension_acquire
doit extension_prepare
doit extension_analyze
```

A second `doit compile_report` is expected to be a no-op.

To remove generated data, report artifacts, workflow state, and local test
caches while preserving `.env`, `_data/input`, and tracked sources:

```bash
doit clean --dry-run  # Preview its scope without deleting anything:
doit clean
```

## Data and Outputs

All provider and generated datasets are ignored:

```text
_data/raw/                    provider caches
_data/normalized/             normalized source contracts
_data/processed/              processed core and extension panels
_output/extension/            regional and Section 9 analysis outputs
reports/tables/               generated core publication tables
reports/tables/appendix/      full machine-readable regression details
reports/figures/              generated core figures
reports/paper/generated/      generated findings, captions, and extension TeX
reports/build/main.pdf        final report
```

Tracked files include source manifests, schemas, immutable paper targets, and
small synthetic test fixtures. No provider bytes or generated datasets are
tracked.

## Empirical Contract

Historical replication uses:

- CRSP `vwretd` market returns and `t30ret` 30-day Treasury-bill returns;
- quarterly sums of monthly `log1p` returns;
- the 10-year minus 3-month Treasury term spread;
- the current bill return minus the prior four-quarter mean;
- Newey-West lags `max(1, horizon - 1)`.

Paper targets and tolerances remain fixed. The generated audit currently has
24 strict passes, 15 revised-vintage passes, and no failures.

## Verification

```bash
python -m pytest -q
ruff check .
ruff format --check .
git diff --check
doit list
doit compile_report
```

The final report gate also checks compact publication tables, appendix
longtables, unique exhibit labels, source/citation validity, relative artifact
paths, a clean final TeX log, and absence of literal `NaN` in main table TeX.
