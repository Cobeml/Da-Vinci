# Implementation record: managed request authoring (Prompt 5)

Implemented on 2026-10-01 on top of Prompts 1–4. Public contracts, compatibility and user commands are in [managed-requests.md](managed-requests.md).

## Decisions

- Added an automatic managed stage controller beneath the existing `ManagedDriver` and workspace worker. It composes `Lifecycle` plan, reference-build, verification, freeze, candidate, simulation, reflection, revision and report operations. No parallel physics engine, service, database migration or model-provider framework was introduced.
- Added typed `ManagedRequest`, `SearchPolicy`, `RequirementsOutput`, `TestPlanOutput`, `SetupOutput`, `DiagnosisOutput`, `StageInput` and `Answers`, shipped in the installed schema catalog. `davinci managed` and localhost HTTP expose request creation, progress, clarification, results/report and cancel/resume. Existing manual managed operations cannot advance an automatic request; external drivers never enter its proposal/reflection loop.
- Persisted stage outputs, repair counts, focused questions/answers, source inspection, operation IDs, conservative solver reservations and stopping reasons. Provider responses keep their existing paid-call checkpoints and accounting. Structured validation failures have distinct bounded repair IDs; uncertain/received requests cannot repeat automatically. A completed provider response can be reused after a crash before stage application.
- Chose one honestly scoped trusted recipe: static rectangular cantilever mass/stress/deflection screening. Model-authored requirements and implementation are constrained to locally validated physical inputs, units, coverage, fixed interface and immutable thresholds. Unsupported phenomena/materials stop before modeling. This is not general FEA or arbitrary evaluator certification.
- Trusted references are host-owned closed-form values; evaluator execution uses isolated CadQuery/NumPy. Verification includes passing/failing fixtures and displaced-root invalid geometry. Independent BRep inspection checks every candidate's rectangular geometry and root, and host-side comparison checks its measurements against the algebraic oracle. Neither a model `passed` field nor another reasoning role is physical verification.
- Draft setup repairs create new evaluator identities; failed reference evidence is retained. Post-freeze defects open bounded linked revisions, record the explanation, reverify and rerun affected sources/parameters. Parent suites/results remain immutable. Corrections carry remaining model budget and prior solver reservations forward.
- Added bounded thickness bisection for the supported monotone recipe; conceptual proposals remain model-authored. Acceptance, optional target, candidate limit, stall and budgets remain separate. Passing baseline tests do not prematurely stop default optimization. A fresh final suite rerun is mandatory for the report's final accepted IDs.
- Scoped existing-part inspection is supported through source experiment/candidate IDs. Automatic edits require compatible regression tests/materials/interfaces before freeze. Other regression changes require a separately verified plan rather than silently inheriting a prior pass.
- Memory uses the shared scoped service; observations are committed evidence and reflections remain hypotheses. Generation and embeddings stay independent. The shipped disabled/local-hash adapters have explicit zero API embedding cost and no downloads.
- Existing v1 configurations, v2 manual experiments, custom tasks, archived studies and browser gallery remain available. Additive `Verification.expected_status=invalid_setup` supports invalid-geometry fixtures. Updated harness/recipe identities require linked revisions for affected old frozen suites; historical results are not upgraded. No UI redesign was made: new managed authoring is CLI/HTTP, while the browser gallery retains its YAML workflow.

## Checks actually run

- `uv run pytest -m 'not integration' -q`: **145 passed, 27 deselected**. This included 16 new deterministic managed tests covering taskless opening, verification/freeze order, failed/improved candidates, missing inputs, malformed output, invalid evaluator, attempted limit relaxation, unsupported physics/runtime, solver budgets, bounded search, linked evaluator correction, final missing evidence, checkpointed/uncertain paid-call doubles, cancellation/resume and real localhost HTTP ownership. Provider doubles never call a paid service.
- Added one final CLI/service boundary test afterward: `uv run pytest tests/product/test_managed.py -k managed_cli -q`: **1 passed, 18 deselected**. It invokes the real CLI against a localhost service with deterministic provider/solver fixtures. Total deterministic checks run across those commands: **146**. The current complete suite includes that CLI test.
- `DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_managed.py -m integration -q`: **1 passed, 1 skipped, 16 deselected** (before the final CLI test was added). Actual local Docker CadQuery/OCP and NumPy execution verified positive/negative/invalid geometry references, a failing thin design, a passing thicker revision and a fresh final rerun. The provider was deterministic. The skipped check was the separately opt-in paid live smoke. Other native adapter suites were not rerun this phase; CI now includes the new managed native test alongside them.
- After adding conservative per-job runtime-probe overhead, `uv run pytest tests/product/test_managed.py -k 'budget or post_freeze' -q`: **3 passed, 16 deselected**, rechecking bounded search, pre-model budget/capability stops and linked corrections.
- `npm run test:product`: **2 passed**, retaining the existing gallery evaluation/continuation and localhost protections.
- `.venv/bin/ruff check davinci/product tests/product scripts/check_external_install.py` and `git diff --check`: passed.
- `node scripts/build_product_ui.mjs` refreshed packaged documentation using the existing compiled UI. `.venv/bin/python -m build --wheel --no-isolation --outdir /tmp/davinci-managed-dist` built `da_vinci_harness-0.2.0-py3-none-any.whl`.
- `uv pip install --reinstall --no-deps --target /tmp/davinci-managed-wheel-check /tmp/davinci-managed-dist/da_vinci_harness-0.2.0-py3-none-any.whl` and `.venv/bin/python scripts/check_external_install.py /tmp/davinci-managed-wheel-check`: **passed**, verifying the isolated wheel's schemas, managed recipe discovery, keyless external operations and memory portability. This uses the interpreter's existing dependencies; fresh dependency installation remains covered by the CI wheel environment.

No paid generation/embedding call, private Atlas/GridFS operation, remote provisioning or model download ran. The existing Starlette/httpx deprecation warning remains. Current automatic physical support is an analytic beam screen, not lab validation; natural-language interpretation still needs review when a request is ambiguous. Unsupported numerical tuning and unavailable physics remain explicit blocked outcomes.

## Separately opt-in live smoke

Supply `OPENAI_API_KEY` in the environment and explicitly configure model/accounting settings for the chosen model. The test never reads the repository `.env`. Set a budget no greater than $10 and explicitly enable this check:

```bash
DAVINCI_LIVE_SMOKE=1 DAVINCI_LIVE_BUDGET_USD=5 \
  uv run pytest tests/product/test_managed.py -m integration -k live_managed -q -s
```

It requires the local CAD image and may spend up to the configured reservation budget. A clarification or budget/capability block is reported as such; smoke-test completion is not a physical acceptance claim. Without `DAVINCI_LIVE_SMOKE=1`, it stays skipped even when credentials happen to exist.
