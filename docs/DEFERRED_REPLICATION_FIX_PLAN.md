# Deferred Replication Fix Plan

## Blockers

- Restore WRDS account access for CRSP inputs.
- Install a TeX distribution that provides the `latexmk` executable. The Python requirement alone may not provide it.

## Steps

1. Acquire WRDS data and validate all real source caches.
2. Run `doit bootstrap_real_data` and confirm all 184 historical quarters.
3. Generate and inspect the 32 pre-PDF artifacts.
4. Resolve or document every Table R1 diagnosis and revised-vintage pass.
5. Run the notebook and export HTML.
6. Run `doit compile_report` and review the PDF, metadata, captions, samples, and artifact hashes.

## Complete When

- No unexplained `FAIL_REQUIRES_DIAGNOSIS` remains.
- Notebook and report builds succeed from real data.
- A person reviews the historical tables and final PDF.
