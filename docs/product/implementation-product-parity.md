# Implementation record: installed workflows and parity (Prompt 6)

Implemented on 2026-10-01, building on the lifecycle, external, simulation, experience and managed services. Complete user commands are in [product-journeys.md](product-journeys.md).

## Contracts and ownership

- The installed `ui/` now offers built-in request authoring, external-agent drafts and the existing advanced YAML/custom-task workflow. Both v2 drivers use the same object/run views, typed results, coverage, capabilities, assumptions, artifacts, lessons and reports. Pending engineering questions are persisted and answered through the managed service. Browser records contain no configured credentials; generation credentials remain on the server.
- `GET /api/v2/workspace/connection` exposes localhost connection details and installed instruction/schema locations. `/api/v2/workspace/objects` and its object-detail route are read-only projections of existing storage. They do not create evidence. Execution completion, acceptance under stated tests, final evidence and optional targets are displayed separately.
- `POST /api/v2/experiments/{id}/handoff` accepts the versioned `Handoff` command: actor, revision, operation ID, new driver/actor, reason and search policy. The corresponding `davinci experiment handoff` command is an HTTP client. Atomic revision/owner checks reject competing advancement; old-owner retries of the identical completed operation are read-only. Handoff is limited to frozen, idle, noncompleted checkpoints, never an active/queued job or an uncertain interrupted stage.
- `POST /api/v2/experiments/{id}/continue` accepts `ContinueExperiment`: actor, revision, operation ID, candidate ID, new driver/actor, focus, budget and policy. `davinci experiment continue` creates a linked experiment with identical frozen tests and a submitted seed. No design results are inherited: the new driver must evaluate again. Reference-verification origin and parent history remain recorded. Retrying after an interrupted creation resumes its deterministic child.
- Managed adoption preserves the suite, spending and solver reservations. Externally driven experiments never enter managed proposal/reflection calls. Adoption supports agent proposals against an existing verified suite; automatic coordinate search requires verified recipe requirements. An evaluator defect in an adopted custom suite stops for an externally verified linked revision instead of guessing reference evidence.
- A trusted, resource-bounded sandbox conversion creates interactive GLB from the evaluated STEP. Candidate code does not produce the viewer asset. Preview logs use distinct artifact names, preserve build logs, and participate in the existing quota and checksum manifest. A preview is not physics evidence.

## Compatibility and packaging

No database migration, hosted service, second execution owner or new model provider was added. Additive ownership history, continuation provenance and projections coexist with v1 records. Legacy YAML runs use their original view and compatibility path; historical acceptance is not upgraded to test-first evidence. Archived studies and the separate `web/` application are unchanged.

The trusted preview changes the frozen execution identity. Previously frozen suites whose stored execution identity differs cannot execute silently under new harness code: create a linked plan revision and reverify. Existing evidence remains inspectable and unchanged. Handoff/continuation do not bypass that check.

Setuptools discovery now includes `davinci.*` and `sandbox.*`, rather than excluding future subpackages. Schemas, adapter metadata, agent instructions, reference resources, UI and rendered documentation ship in the wheel. Source distributions include UI/docs and the installed-package/native verification scripts.

## Checks actually run

- `uv run pytest -m 'not integration' -q`: **152 passed, 28 deselected**. Deterministic orchestration includes ownership races, external-provider isolation, continuation, clarification, capability failures, immutable suites and report semantics. This is not physical validation.
- `uv run python scripts/required_native.py`: **11 passed, 1 skipped, 41 deselected**. Actual local Docker CadQuery/OCP, beam NumPy and existing adapter checks executed. The skipped check was only the separately opt-in paid-model smoke test. CI now fails if expected images are unavailable or core reference/managed/parity tests are missing or skipped.
- `npm run test:product`: **5 passed**. Browser flows cover keyless external failing/improved CAD, managed request/clarification/report, missing solver, continuation/handoff, interactive v2 geometry and legacy viewing/YAML validation. Reasoning is a deterministic test provider; CAD executes in the real sandbox.
- `npm run build:ui`, Ruff and `git diff --check`: passed. Inspected the browser screenshot of the managed report.
- Built the wheel and installed its dependencies in a new `/tmp/davinci-product-parity-venv` environment. From `/tmp`, `scripts/check_installed_routes.py` completed both public routes with native CAD, reports, matching candidate/suite/runtime identities and trusted GLB. It asserts imports resolve to installed `site-packages`, not the checkout. The existing `check_external_install.py` also passed installed CLI startup/reconnection, schema/instruction/adapter discovery and keyless memory export/import. Rebuilt wheel and sdist after documentation updates and checked required code/resources/UI/docs and absence of runtime, `.env` and bytecode files.

Native parity uses identical status/units and metric tolerance **1e-6 absolute or 1e-8 relative** for the analytic beam screen. Both routes execute independently; scores are not copied. This demonstrates parity for these fixed inputs, not improved engineering performance or generic solver equivalence.

No paid generation/embedding, private Atlas/GridFS, cloud provisioning or model download ran. Automatic new-task authoring remains limited to the verified rectangular-beam analytic recipe. Other templates retain their explicit screening scope. The existing Starlette/httpx test deprecation warning remains.

## Reproduction

From a development checkout with dependencies installed:

```bash
npm run build:ui
uv run pytest -m 'not integration' -q
uv run davinci setup --template vtol
uv run python scripts/required_native.py
npm run test:product
uv build --no-build-isolation --out-dir /tmp/davinci-product-parity-dist
uv venv /tmp/davinci-product-parity-venv
uv pip install --python /tmp/davinci-product-parity-venv/bin/python /tmp/davinci-product-parity-dist/da_vinci_harness-0.2.0-py3-none-any.whl
```

From `/tmp`, replacing `/path/to/Da-Vinci` with the checkout path (the scripts import only the installed product):

```bash
/tmp/davinci-product-parity-venv/bin/python /path/to/Da-Vinci/scripts/check_installed_routes.py
/tmp/davinci-product-parity-venv/bin/python /path/to/Da-Vinci/scripts/check_external_install.py /tmp/davinci-product-parity-venv/lib/python3.11/site-packages
```

For complete user journeys, follow [external coding agent](product-journeys.md#external-coding-agent-no-model-key-or-database) or [built-in description to report](product-journeys.md#built-in-agent-description-to-report). Paid-model testing remains a separate explicit, budgeted opt-in documented in the managed implementation record.
