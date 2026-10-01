# Lifecycle foundation implementation record — 2026-10-01

Implemented the provider-independent lifecycle beneath `davinci/product.Engine`. Decisions for later phases:

- Use existing `runs` documents as atomic experiment aggregates, existing Store CAS, shared execution slot, Runner, Git source snapshots, and Artifacts/GridFS. Do not create a second scheduler or storage engine.
- Use protocol version 2 for new Python/HTTP contracts. Leave version-1 YAML and gallery behavior behind an explicit compatibility adapter; never relabel historical studies as test-first.
- Separate plan, evaluator, pinned runtime, harness implementation, suite, and candidate identities. Freeze only after coverage and positive/negative reference verification; corrections open linked drafts with no inherited pass evidence.
- External drivers require no model provider. Managed author/propose/reflect operations call the same lifecycle services, preserve provider spending/checkpoints, and expose missing requirements through `awaiting_input`.
- Persist owner, operation receipts, revision, phase, job tokens and evidence in one atomic document. Do not expire/reassign execution leases automatically. Recovery runs only during exclusive server startup.
- Make embeddings opt-in. Retain local lexical experience retrieval, including explicitly unverified legacy hypotheses.
- Keep result completion, evidence completeness, physical acceptance and optional objective targets separate. Preserve failure classes and fail closed on missing evidence.

The public contracts, routes, evaluator protocol, restart semantics, limitations, and compatibility rules are in [Experiment lifecycle](lifecycle.md).

Checks actually run:

- 82 non-integration tests passed, with 21 integration tests deselected.
- All 5 product Docker integrations passed. The new v2 beam test was rerun after final evidence/numeric hardening: 1 passed, 4 deselected.
- Both existing product browser checks passed (create/evaluate/continue and invalid/cross-origin request rejection).
- The bundled Next.js UI/docs production build and Ruff checks passed.
- A pre-existing Starlette/httpx deprecation warning remains; it did not fail the checks.

Validation commands (run from the repository root):

```bash
uv run pytest -m 'not integration' -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py -k v2 -q
npm run build:ui
npm run test:product
.venv/bin/ruff check davinci/product davinci/runner.py tests/product
```

The physical integration test uses real CadQuery/OCP STEP generation and a NumPy Euler-Bernoulli stiffness solve checked against independent closed-form reference values. It is a restricted linear beam screen, not general finite-element or hardware validation. The four existing packaged sensor/gripper/VTOL/custom baseline integrations are also retained. Default automated tests use deterministic runner/provider fixtures.

No paid model calls, private database calls, deployment, or changes to archived evidence are part of this phase. Atlas CAS/GridFS uses the existing abstractions but is not live-tested here. Subsequent phases can add the v2 gallery and task/fixture authoring UX; this phase exposes the lifecycle through Python and localhost HTTP. Automatic convergence campaigns, semantic mesh generation, and scientific verification of arbitrary evaluator code remain outside this phase.
