# Packaged `cay_lab` Workflow Convergence Plan

**Status:** Blocked implementation plan and single source of truth

This file supersedes all earlier convergence design and planning documents.
Update this file rather than creating another convergence document.

## Blocker: Pin Extension Sources First

Do not start the package migration until a clean checkout can reproduce the
current extension results without reading tracked files from `cay_data/raw`.

Before Stage 1:

1. Add `config/extension_sources.yml` with source IDs, URLs or API queries,
   release or vintage dates, units, coverage, SHA-256 hashes, and immutable
   archive or import locations.
2. Pin the exact June 2026 Z.1, DFA, and FRED inputs. Fail on a hash mismatch;
   never substitute the latest release.
3. From an empty temporary data root, acquire the pinned inputs and rebuild all
   six extension datasets byte-for-byte.
4. Reproduce the prepared and rolling result hashes in the Baselines section.
5. Confirm all 438 regional rows still use `income_share_fallback`. Do not
   enable the unused FDIC path.

Current source gaps:

| Source | Blocker |
|---|---|
| Z.1 S14.b and S1M.b | Local CSVs have no acquisition path |
| DFA net-worth detail | `dfa.zip` points to a mutable latest release |
| FRED HPI/PCPI/POP | Series are not pinned to an ALFRED vintage |
| FDIC deposits | The unused helper must remain disabled |

Required seed hashes:

```text
Z.1 S14.b: 95b95ece9bcb43a5bc2c9313dc5c9b1f8d9874983a9dbfde666bb34f89606f45
Z.1 S1M.b: 751291a66e349524d6bdbc5827e0a5f085c4c2340809d621f09da2fb00b44421
DFA ZIP:    a7804fb240cb6153d6beb04335ac558cb4e0c5c2ba221eba7c41b9c62ce36274
```

Add the ten current FRED snapshot hashes to the manifest. Keep `cay_data/raw`
tracked until this gate passes.

## 1. Goal

Convert the repository to a classic installable Python `src` layout with one
package, `cay_lab`, while keeping root `tests/`, project configuration, data,
notebooks, reports, and PyDoit entry points.

The core replication and extension will share one environment, one installed
package, one settings layer, and one root workflow.

This structural migration must not change:

- core replication data, estimates, artifacts, or audit results;
- extension source definitions, formulas, defaults, rows, statistics, or output
  content;
- plain `doit`, which remains core-only.

## 2. Final Project Structure

```text
Study_of_Cay_and_Predictivity_Lab/
|-- pyproject.toml
|-- environment.yml
|-- README.md
|-- WORKFLOW_CONVERGENCE_PLAN.md
|-- dodo.py
|-- settings.py
|-- chartbook.toml
|-- ruff.toml
|-- .env.example
|-- .gitignore
|-- src/
|   `-- cay_lab/
|       |-- __init__.py
|       |-- settings.py
|       |-- pipeline.py
|       |-- bootstrap_real_data.py
|       |-- tasks.py
|       |-- data/
|       |-- analysis/
|       |-- reporting/
|       `-- extension/
|-- tests/
|-- config/
|-- docs/
|-- notebooks/
|-- reports/
|-- _data/       # ignored
`-- _output/     # ignored
```

`src/` is not a package: remove `src/__init__.py`. Keep tests and project assets
at the repository root. Keep root `dodo.py` and `settings.py` as thin imports
from `cay_lab`.

## 3. Packaging Contract

Use `pyproject.toml` only for build and package metadata:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "cay-lab"
version = "0.1.0"
requires-python = ">=3.11"

[tool.setuptools.packages.find]
where = ["src"]
include = ["cay_lab*"]
```

Do not package `_data`, `_output`, config, reports, notebooks, or tests.

### Environment

Use `environment.yml` as the only runtime and development dependency list. It
must include Python 3.11, `setuptools>=68`, pip, and non-Python tools such as
Tectonic. Do not add `project.dependencies` to `pyproject.toml`.

The `build-system.requires` entry in `pyproject.toml` is mandatory PEP 517 build
metadata. Keep its Setuptools version aligned with `environment.yml`.

Install the package from the repository root after creating the environment:

```bash
mamba env create -f environment.yml
mamba activate cay
python -m pip install --no-deps --no-build-isolation -e .
```

### Import check

The import check in Section 7 must resolve to
`<repository>/src/cay_lab/__init__.py`. Tests, notebooks, PyDoit, and module
commands must import the installed package. Do not set `PYTHONPATH` or modify
`sys.path`.

## 4. Execution Rules

1. Use `git mv`. Make one dependency-layer move per commit.
2. Do not change algorithms, formulas, defaults, or output names in move commits.
3. Shared modules must not import `cay_lab.extension`.
4. Add temporary import shims only when needed; delete them in Stage 9.
5. Run the stage gate before starting the next stage.

## 5. Baselines That Must Not Change

### Core

```text
Python: 3.11
Pytest cases collected: 137
Review result: 136 passed; orchestration case blocked only by unavailable doit
Processed panel SHA-256:
0d6643bd2eea7b47f61c8dcd74f4374cc9d1025a5b8fa5f07a1c95f5d4abe485
Generated table files: 16
Generated figure files: 9
Pre-PDF artifacts: 32
```

Also preserve semantically:

- Table R1 rows and statuses;
- selected risk-free and term-spread conventions;
- historical and updated sample dates;
- generated table values and shapes;
- figure input data;
- report section/exhibit inventory;
- notebook execution.

Timestamp-, Git-, or PDF-metadata-bearing files need not match bytes.

### Extension

All six rebuilt extension datasets currently match byte-for-byte.

```text
prepared rows: 417
prepared range: 1991Q2-2025Q4
rolling rows: 297
rolling range: 2001Q2-2025Q4
segments: bottom50, middle40, top10
status counts: ACTIVE 194, WEAKENED 57, LOST 46
mean absolute error: 0.02233142675849002
```

```text
prepared CSV SHA-256:
73644f47d9eb23d256a1400f1bf6bcafed9b2f4ff6bd7ae75160623927eb3568

rolling CSV SHA-256:
db855e9510cda1955b56a14673d5c0c47cc60fd904060b556d077461a8ec7731
```

The chartbook remains four pages with the same summary and three segment pages.
PDF bytes may differ. The focused extension suite has 29 passing cases.

Store these expectations in `tests/fixtures/migration_baseline.json`; do not
commit generated licensed data.

## 6. Migration Stages

### Stage 1: Establish packaging and guardrails

- Add `pyproject.toml` and `setuptools>=68` to `environment.yml`.
- Add migration baseline fixtures and validators.
- Move the root package:

```text
cay_lab/ -> src/cay_lab/
```

- Remove copied caches, install editable, and check `cay_lab.__file__`.
- Add a test that rejects shared-module imports of `cay_lab.extension`.

Until Stage 7, run the moved extension workflow with
`doit -f src/cay_lab/dodo.py`. Do not recreate root `cay_lab/`; it would shadow
the installed package.

**Gate:** import location, current tests, and both baselines pass.

### Stage 2: Isolate extension-only code

Within `src/cay_lab`, move:

```text
data/loader.py                    -> extension/loader.py
analysis/decomposition.py         -> extension/decomposition.py
analysis/predictive_regression.py -> extension/predictive_regression.py
monitor/rolling_monitor.py        -> extension/rolling_monitor.py
dodo.py chartbook functions       -> extension/workflow.py
```

Keep `analysis/cay_builder.py` shared. Add a re-export shim only when its
consumer cannot move in the same commit.

Preserve target timing: `prediction_window=1` creates an already forward-aligned
target, so the chartbook intentionally calls the legacy regression with
`horizon=0`.

**Gate:** 29 extension tests, both extension hashes, metrics, and the moved
extension workflow pass.

### Stage 3: Move extension builders into the package

Move:

```text
cay_data/build_components_from_s14.py -> src/cay_lab/extension/build_components.py
cay_data/build_extension_data.py      -> src/cay_lab/extension/build_datasets.py
```

Keep script wrappers only until module commands and root tasks work.

**Gate:** builder modules reproduce all six baseline datasets byte-for-byte
from the pinned clean-room raw cache.

### Stage 4: Move settings and core data

Move:

```text
src/settings.py -> src/cay_lab/settings.py
src/data/*.py   -> src/cay_lab/data/*.py
```

Root `settings.py` imports `cay_lab.settings`. Keep old `src.*` shims only for
consumers that move later.

Test root discovery for `config`, `reports`, `_data`, and `_output`, including a
command run outside the repository.

**Gate:** settings, acquisition, contracts, transformations, panel tests, source
metadata, core panel baseline, and import boundaries pass.

### Stage 5: Move core analysis

Move all current `src/analysis/*.py` modules into
`src/cay_lab/analysis/`. `estimate_cay` uses the shared `cay_builder`.

Keep `cay_lab.analysis.forecasting.run_hac_regression` unchanged. Do not merge
the core and extension regression implementations.

**Gate:** CAY modes, conventions, Tables II/III/VI/R1, figures, and both product
baselines pass.

### Stage 6: Move reporting, pipeline, and bootstrap

Move:

```text
src/reporting/*.py         -> src/cay_lab/reporting/*.py
src/pipeline.py            -> src/cay_lab/pipeline.py
src/bootstrap_real_data.py -> src/cay_lab/bootstrap_real_data.py
```

Keep temporary old-namespace shims. Preserve artifact IDs, paths, schemas,
captions, dependencies, and LaTeX content.

Run:

```bash
python -m cay_lab.settings
python -m cay_lab.pipeline panel
python -m cay_lab.pipeline exhibits
python -m cay_lab.pipeline report
python -m cay_lab.bootstrap_real_data --compile-report
```

**Gate:** 32 artifacts, 16/9 table/figure files, audit semantics, notebook, PDF,
module commands, temporary old commands, and both baselines pass.

### Stage 7: Centralize PyDoit

Move task implementations into `src/cay_lab/tasks.py`. Root `dodo.py` imports
`DOIT_CONFIG` and each `task_*` function.

Add `config/extension.yml` and root tasks:

```text
extension_acquire
extension_data
extension_chartbook
extension
```

Ownership:

```text
extension_acquire   -> pinned raw cache and metadata
extension_data      -> normalized/processed extension data
extension_chartbook -> prepared CSV, rolling CSV, chartbook PDF
extension           -> aggregate task with no target
```

Plain `doit` remains core-only.

**Gate:** task discovery, target ownership, dependency order, failure behavior,
freshness, no-op second run, and both baselines pass.

### Stage 8: Migrate consumers and data paths

Update tests, root entry points, README, notebooks, report docs, Chartbook
metadata, and CI commands to `cay_lab` paths.

After source acquisition passes, move extension data into:

```text
_data/raw/extension/
_data/normalized/extension/
_data/processed/extension/
_output/extension/
```

Track source manifests, hashes, schemas, and small synthetic fixtures. Ignore
raw and processed extension data. Set Ruff first-party imports to `cay_lab`.

**Gate:** no real consumer imports an old path; clean-room acquisition and both
baselines pass from the new paths.

### Stage 9: Remove shims and dead trees

Delete in order:

1. old `src.analysis`, `src.data`, `src.reporting`, settings, pipeline, and
   bootstrap shims;
2. `src/__init__.py`, leaving `src/` as a non-package source container;
3. old extension module shims and empty `src/cay_lab/monitor`;
4. `src/cay_lab/dodo.py` and builder wrappers;
5. `cay_data/` after ignored-data clean-room reconstruction and any Git-history
   cleanup are approved.

Final searches must show:

```text
no tracked Python import begins with src
no shared module imports cay_lab.extension
no Python implementation exists outside src/cay_lab except thin root entry points
src contains only cay_lab and packaging metadata artifacts
cay_data is absent
```

**Gate:** run full core and extension checks after each deletion batch.

## 7. Validation

Run after each applicable stage:

```bash
python -c "import cay_lab; print(cay_lab.__file__)"
python -m pytest
ruff check .
doit list
```

Run plain `doit` and `doit extension` after Stage 7, then rerun both to verify a
no-op second run. Run the core and extension baseline validators before each
commit and before deleting a shim.

## 8. Out of Scope

Do not include these changes in the migration:

- econometric, formula, sample, or default changes;
- latest-vintage source refreshes;
- HAC implementation consolidation or bug fixes;
- extension content in the core report;
- fabricated template or contribution provenance.

Core Table R1 must not depend on extension data. Keep
`report.include_extension` false.

## 9. Completion Checklist

- [ ] `pyproject.toml` defines the installable `cay-lab` project.
- [ ] Editable installation resolves `cay_lab` from `src/cay_lab`.
- [ ] Root `tests/` exercise the installed package without path manipulation.
- [ ] Extension sources reacquire from an empty ignored data root with pinned hashes.
- [ ] All application implementation is under `src/cay_lab`.
- [ ] `src/__init__.py`, old `src.*` packages, root `cay_lab`, and `cay_data` are absent.
- [ ] Root `dodo.py` and `settings.py` are thin entry points.
- [ ] Module commands and root tasks work.
- [ ] Plain `doit` remains core-only.
- [ ] Shared modules never import extension modules.
- [ ] Core panel, audit, samples, conventions, and artifacts match baseline.
- [ ] Extension data, CSV results, metrics, and chartbook content match baseline.
- [ ] Tests, Ruff, notebook, and report checks pass.
- [ ] README documents one environment, editable install, and both workflows.
- [ ] Source provenance, hashes, proxy status, and fallback behavior are explicit.
- [ ] No compatibility shim remains unless an external consumer is documented.

Migration is complete when a clean checkout can create the environment, install
the package, and reproduce both workflows and baselines from root commands.