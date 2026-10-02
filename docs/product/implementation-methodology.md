# Phase 9 implementation record

Implemented an additive attributed-evidence service on the existing Engine/Store/Artifacts and localhost API. Measurements never enter trusted simulation results. Immutable specimen allocations keep calibration/held-out partitions separate; unit-aware residuals, descriptive versioned offsets, negative validation outcomes and portable origin/integrity records remain inspectable. No database migration, provider dependency, new scheduler or archived-study rewrite was introduced.

The methodology audit found two retrieval boundary gaps: lifecycle lookup by a known experiment ID needed the current workspace/project check, and held-out experiments needed a fixed reusable-memory allowlist to exclude task answers generated in another arm. Both are enforced centrally, and tests cover managed/external callers with an ambient unused model key. The worker queue query is also scoped so a foreign-project queued experiment cannot reach the new lookup fence and interrupt local dispatch. A live benchmark poll was also corrected to wait through the persisted `running` stage instead of treating it as completion.

Public contracts are documented in [measurements](measurements.md), the installed schemas and agent instructions. [Methodology](methodology.md) documents the benchmark, budgets and interpretation. New code is packaged under `davinci.product`; the scripts only start the ordinary service or invoke public HTTP operations. CI keeps fast checks separate and explicitly builds/requires native solver images for the benchmark. Default CI never runs live model calls.

## Migration and restart behavior

Existing v1 configurations/records still use the compatibility adapter; no historical test-first guarantee is added. New evidence collections and optional retrieval metadata are additive. Existing measurements/results are not rewritten. The lifecycle scope fix changes the trusted execution identity: previously frozen v2 experiments may be inspected, but extending their execution after this update requires an explicit linked revision and renewed verification under the new identity. Never replace archived manifests to suppress the mismatch.

The service still owns all lifecycle execution and cancellation. Benchmark controllers do not write experiment tables directly. A stopped controller leaves server-owned evidence intact; inspect its job/status before resuming operations with the original IDs, or start an explicitly new campaign in a new workspace. The fixture server uses the same workspace lock and cannot compete with an existing service.

## Reproduction and checks

```bash
uv run pytest -m 'not integration' -q
uv run python scripts/required_native.py
uv run python scripts/required_native.py --structural
uv run python scripts/run_methodology_benchmark.py \
  --workspace runtime/methodology-validation --output runtime/methodology-validation-results
npm run build:ui
uv build --no-build-isolation
uv venv /tmp/davinci-methodology-wheel
uv pip install --python /tmp/davinci-methodology-wheel/bin/python dist/*.whl
cd /tmp
/tmp/davinci-methodology-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_methodology.py \
  --workspace /tmp/methodology-wheel-workspace --output /tmp/methodology-wheel-results --skip-structural
/tmp/davinci-methodology-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_routes.py
```

Use a new workspace/output path when rerunning a completed campaign. Native evidence includes scoped beam/CAD execution and optional Gmsh/CalculiX bracket cases. Solver setup commands and exact scope are in the linked simulation documentation. JSON benchmark summaries retain image and acceptance-contract identities, report hashes, counts, costs and negative outcomes. Full raw artifacts stay in the reproducible workspace and CI uploads.

Checks actually run on 2026-10-02:

- Full fast suite: **177 passed, 40 deselected**; subsequently added independent live-protocol oracle and scoped-worker checks passed in a **17-test** focused methodology/external suite.
- Native CAD/route/tool gate: **12 passed**, one explicitly opt-in live-model test skipped; required core checks executed.
- Native structural gate: **11 passed**, six non-native tests deselected; no structural check skipped.
- Full native methodology benchmark: **12 modeled cases**, six paired cross-driver physical-contract/metric comparisons, four unavailable requests, two deliberately bad evaluator cases, and synthetic comparison/export/import through both routes.
- Fresh wheel outside the checkout: **10 modeled beam/edit cases** with both drivers and five parity comparisons; schema/docs discovery and synthetic evidence round-trip passed without host solver extras. Structural execution was explicitly omitted from this installed benchmark because the full native structural run was recorded separately.
- Separate installed automatic managed request-to-report and keyless external journey passed with the same-suite parity check, STEP-derived GLB, deterministic reasoning and native CAD.
- Added memory/evidence/methodology audit checks: **21 passed** before the additional oracle test. Ruff checks, UI/docs build, wheel/sdist build and `git diff --check` passed.

The installed benchmark was repeated successfully after the direct-memory-search policy tightening (`/tmp/methodology-wheel-final-results`). The subsequent worker queue scope filter is covered by the focused 17-test check. No native solver code or acceptance contract changed after the native run. No live-model calls, private database access or real laboratory measurements were used. The remaining limitations are listed in the [capability matrix](capability-matrix.md).
