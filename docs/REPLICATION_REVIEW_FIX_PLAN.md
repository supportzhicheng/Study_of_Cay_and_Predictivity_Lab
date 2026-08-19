# Essential Replication Fix Plan

## Goal

Make the core Lettau and Ludvigson replication numerically correct, reproducible, and supported by one real-data build before starting extension work.

## Current Evidence

- Python 3.11.12 was used.
- Pytest collected 126 cases: 125 passed and one failed only because `doit` was unavailable in the review environment.
- Ruff and the declared formatting checks passed.
- The synthetic integration test generated all 32 required report artifacts.
- No real processed panel, empirical audit, or final PDF was present.

Therefore, the architecture is substantially recreated, but the empirical replication is not yet demonstrated.

## 1. Fix The PCE Deflator Scale

**This is the numerical blocker.**

`src/data/normalize_sources.py` currently deflates nominal wealth and labor income with:

```text
nominal / pce_price_index / population
```

The acquired FRED series is `PCECTPI`, an index expressed around 100. Use:

```text
nominal / (pce_price_index / 100) / population
```

With nominal wealth 200, price index 100, and population 2, real wealth per capita should be 100, not 1.

### Required checks

- A price index of 100 leaves a nominal level unchanged before the per-capita division.
- A price index of 200 halves the real level.
- Wealth and labor income use the same convention.
- Test fixtures use realistic index points such as 100 or 110.
- BEA consumption units are confirmed before deciding whether it needs deflation.

### Done when

The corrected tests fail against the old formula, pass against the new formula, and current-vintage macro log levels have plausible scales.

## 2. Make Generated Evidence Truthful

### Artifact lineage

The artifact manifest currently records only the report contract and paper targets. Every empirical artifact must also depend on:

```text
_data/processed/core_quarterly.parquet
_data/processed/core_quarterly.metadata.json
reports/captions.yml
```

Changing the panel or captions must make affected artifacts stale.

### Sample dates

Do not use one broad updated endpoint for every exhibit. Derive dates from the observations actually used by each table or figure.

A reproduced review case had Table III row 8 ending at `2003Q4` while its caption claimed `2005Q1`.

For tables whose rows or horizons differ, either enforce one common sample or disclose the row/horizon-specific range.

### Updated takeaways

Generate takeaways from exhibit values rather than generic prose. At minimum report:

- the most persistent updated predictor for Table II;
- the historical-versus-updated CAY result for Table III;
- the strongest updated horizon for Table VI;
- strict, revised-vintage, and diagnosis counts for Table R1.

### Done when

Tests prove that changing panel/caption inputs triggers stale detection and that truncated source coverage cannot produce an overstated caption endpoint.

## 3. Repair The Build Graph

The current PyDoit graph assigns `reports/build/artifact_manifest.json` to both `generate_exhibits` and `bootstrap_real_data`. A target must have one owner.

Use this ownership:

```text
build_panel          -> processed panel and panel metadata
generate_exhibits    -> 32 pre-PDF artifacts, including artifact manifest
run_notebook         -> executed notebook and HTML
compile_report       -> main PDF and LaTeX log
run_tests            -> test XML
bootstrap_real_data  -> aggregate task or unique completion marker
```

Required edges:

```text
source preparation -> build_panel -> generate_exhibits
                                      |-> run_notebook
                                      `-> compile_report
```

`generate_exhibits` must also depend on targets, captions, and report configuration. `compile_report` must depend on generated artifacts and every LaTeX/BibTeX source file.

### Done when

With `doit` available:

1. each target has one owner;
2. requesting a downstream task builds its prerequisites;
3. touching panel, captions, targets, or report source reruns the correct tasks;
4. a second unchanged run is up to date.

## 4. Run The Real Replication

After Sections 1-3:

1. acquire or import validated real sources;
2. build the normalized caches and processed panel;
3. generate all 32 pre-PDF artifacts;
4. inspect `table_r1_replication_audit.csv` and `replication_status.txt`;
5. execute the notebook;
6. compile the report when `latexmk` is available.

Do not call the project successfully replicated merely because synthetic tests pass.

### Done when

- all 184 historical quarters are present;
- no `FAIL_REQUIRES_DIAGNOSIS` remains unexplained;
- revised-vintage passes are documented;
- report metadata contains the expected samples, vintage, and selected conventions;
- all artifact hashes and dependencies are recorded;
- the generated historical tables and report have been reviewed by a person.

## Core Gate Before Extension Work

Proceed to extension integration only when:

- [ ] PCE scaling and realistic unit tests are correct.
- [ ] All deterministic tests, Ruff, and formatting checks pass.
- [ ] PyDoit has one target owner and correct dependency edges.
- [ ] Manifest dependencies and exhibit sample dates are truthful.
- [ ] Updated takeaways are calculated.
- [ ] A real processed panel and all 32 artifacts exist.
- [ ] Table R1 has no unexplained failures.
- [ ] The notebook runs and the report compiles when tools are available.

## Recommended Order

1. Correct macro units and tests.
2. Correct artifact lineage, dates, and takeaways.
3. Correct the PyDoit graph.
4. Run and review the real empirical build.
5. Approve one extension analysis using `EXTENSION_AUTHOR_QUESTIONS.md`.
