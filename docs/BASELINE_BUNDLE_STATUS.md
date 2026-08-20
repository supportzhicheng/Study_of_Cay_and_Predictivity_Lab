# Baseline Bundle Status

The regional baseline rebuild is verified from the migrated local source
caches: 414 prepared rows, 294 rolling rows, and exact recorded CSV hashes.
All regional liquid-share rows use `income_share_fallback`.

The exact Section 9 baseline remains blocked on the pinned QQQ cache declared
in `config/extension_sources.yml`:

```text
rows: 814
coverage: 2023-01-03 through 2026-04-01
SHA-256: ecbcf48746b1167b502d06fd07022f3f2ff7eff69fb89c4d4b08a8853c802bbb
```

The available local latest-mode cache has the required coverage but a different
hash. Baseline mode rejects it instead of silently substituting mutable data.
Place the pinned `QQQ.csv` and the other declared source files under
`EXTENSION_INPUT_DIR` to complete the exact clean-room baseline gate.