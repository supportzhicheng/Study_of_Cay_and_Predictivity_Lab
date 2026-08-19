# Essential Questions For The Extension Author

## Goal

Choose one extension analysis that can run end to end after the core replication gate passes.

## Recommended First Analysis

> Test whether aggregate household wealth composition adds one-quarter-ahead excess-return predictability beyond aggregate CAY.

Start with the household-and-nonprofit aggregate dataset. Defer wealth-group and regional proxy work until this aggregate analysis works from source data through generated table and figure artifacts.

## 1. What Is The Primary Outcome?

Choose one:

- [ ] **Future excess stock returns. Recommended.** This directly extends the paper.
- [ ] Future growth of a wealth component. This is a separate wealth-dynamics study.
- [ ] Other: ________________________________________________

**Author decision:** ________________________________________________

The current prototype predicts future wealth-component growth. It does not test whether composition adds return predictability beyond CAY.

## 2. Which Dataset Is Primary?

Choose one:

- [ ] **Households and nonprofit organizations. Recommended.** Aggregate, long coverage, and a clean quarterly join to the core panel.
- [ ] Households only.
- [ ] Wealth groups.
- [ ] Regional proxy.

**Author decision:** ________________________________________________

If wealth groups are selected, the common market outcome creates repeated observations across groups and needs dependence-aware inference. Regional data must always be labeled as proxy evidence.

## 3. What Exactly Is The Predictor?

Choose and define one representation:

- [ ] component shares of total wealth;
- [ ] changes in component shares;
- [ ] log ratios relative to one omitted component;
- [ ] log component levels;
- [ ] deviations from expanding means, as in the current prototype;
- [ ] other: ________________________________________________

Write the exact formula:

$$
z_t =
$$

____________________________________________________________________

**Author-approved name:** __________________________________________

The current `sub_cay_*` variable is a component's log level minus its expanding mean. It is not a formal decomposition of:

$$
cay_t = c_t - \beta_a a_t - \beta_y y_t.
$$

Unless a derivation and the necessary component-level consumption and labor-income data exist, rename it instead of calling it “sub-CAY.”

If shares are used, omit one component or use a compositional transform because all shares cannot be included with a constant when they sum to one.

## 4. What Outcome, Horizon, And Sample Are Approved?

Recommended defaults:

```text
outcome: core selected S&P excess return
horizon: one quarter
sample: full latest-common-quarter overlap
```

**Outcome:** ________________________________________________

**Horizon:** ________________________________________________

**Sample:** _________________________________________________

For each extension input, confirm when quarter-$t$ data became observable and whether later revisions create look-ahead bias:

____________________________________________________________________

The pipeline must compute the latest common quarter from observed values and must not fill missing observations to extend the sample.

## 5. Which Models Should Be Run?

Recommended minimum set:

### Baseline

$$
r^e_{t+1} = \alpha + \beta cay_t + \varepsilon_{t+1}.
$$

### Composition only

$$
r^e_{t+1} = \alpha + \gamma^\top z_t + \varepsilon_{t+1}.
$$

### Incremental extension

$$
r^e_{t+1} = \alpha + \beta cay_t + \gamma^\top z_t + \varepsilon_{t+1}.
$$

- [ ] Approve these models.
- [ ] Revise them as follows: ______________________________________

Use the core selected excess-return convention and core Newey-West implementation. Do not maintain a second forecasting implementation in the extension.

**Primary evidence of incremental value:**

- [ ] composition coefficients and HAC t-statistics;
- [ ] a joint test that composition coefficients are zero;
- [ ] adjusted $R^2$ improvement over the baseline;
- [ ] out-of-sample forecast improvement;
- [ ] other: ________________________________________________

**Author decision:** ________________________________________________

## 6. What Is The Minimum Product?

Recommended first release:

### Table E1

One table containing the three approved models, coefficients, HAC t-statistics, observations, actual sample dates, adjusted $R^2$, and the approved incremental-value test.

### Figure E1

One descriptive time-series figure of the approved composition predictors with recession shading and a 1998Q3 marker where relevant.

### Isolated outputs

```text
reports/extension/tables/table_e1_incremental_predictivity.{csv,tex}
reports/extension/figures/figure_e1_wealth_composition.{pdf,png,tex}
reports/extension/build/extension_metadata.json
reports/extension/build/extension_artifact_manifest.json
```

- [ ] Approve Table E1.
- [ ] Approve Figure E1.
- [ ] Approve the isolated output namespace.

The extension should reuse the core processed analysis data, selected conventions, forecasting functions, artifact writers, captions, metadata, and hashes. It must not change the core replication audit.

## 7. Is The Data Provenance Approved?

For the selected dataset, provide:

```text
original author/provider:
source URL/publication:
retrieval date or vintage:
license or reuse permission:
direct data or constructed proxy:
transformation owner:
revision policy:
```

Confirm:

- [ ] raw and generated extension files may be retained and shared;
- [ ] attribution language is approved;
- [ ] proxy data is clearly disclosed;
- [ ] no core replication artifact depends on extension data.

## Author Sign-Off

Complete this block before implementation:

```text
primary outcome:
primary dataset:
predictor formula and name:
horizon:
sample:
information-availability decision:
approved models:
primary evaluation criterion:
approved Table E1:
approved Figure E1:
data reuse permission confirmed by:
author approval date:
```

## Go/No-Go Gate

Proceed only when:

- [ ] the core gate in `REPLICATION_REVIEW_FIX_PLAN.md` passes;
- [ ] one primary question and dataset are selected;
- [ ] the predictor has an exact mathematical definition and honest name;
- [ ] timing rules out look-ahead bias;
- [ ] models and evidence criteria are approved before results are inspected;
- [ ] provenance and reuse permission are documented;
- [ ] Table E1 and Figure E1 are approved.

Otherwise, keep the current extension as an exploratory prototype outside the core report.
