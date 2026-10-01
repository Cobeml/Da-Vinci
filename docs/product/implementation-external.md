# External route implementation record — 2026-10-01

This phase builds on [the lifecycle foundation](implementation-lifecycle.md). The [external-agent guide](external-agents.md) documents public commands, HTTP operations, schemas, bundle provenance, exit codes, and a complete failed-design/revision walkthrough.

Decisions:

- Extend `Engine.lifecycle` with durable queued verification, reference-building and evaluation operations. Queue entries, operation receipts, phase and revision are one atomic run-document update. The existing workspace worker consumes explicit physical jobs only; external experiments never enter its managed reasoning loop.
- Keep one local service as execution owner. The CLI uses localhost HTTP, checks workspace identity, and uses the existing server lock plus a startup lock. It never opens Store or Engine for external mutations. There is no second scheduler, database migration, hosted service or MCP dependency.
- Retain old v1 custom files and YAML behavior. Add `--driver external`, packaged agent instructions, schemas, a custom beam example and a public-API walkthrough. Candidate source remains the current `build(parameters, interfaces)` Assembly contract, with explicit source/parameter provenance.
- Return 202 and a job ID for physical work. Preserve job history after completion/cancellation/restart. Reuse operation IDs only with identical payloads; require new explicit operations after interrupted/cancelled work. Queued jobs survive restart; running jobs are fenced as interrupted.
- Treat all external reflections as hypotheses, including evidence-linked prose. Clients cannot submit trusted results, modify a frozen suite or set acceptance. External retrieval never constructs a provider or embedding client.

Migration: HTTP v2 `/verify` and `/evaluate` now return jobs rather than completed run records; clients poll job status and fetch results. Direct synchronous Python methods remain for existing in-process adapters. Existing records are not rewritten. The harness implementation hash changes, so old frozen v2 suites require linked revision/reverification before new execution. The v1 gallery and archived studies remain intact.

Checks actually run:

- 95 non-integration tests passed, including a provider double that raises on construction/calls with both absent and dummy model keys; public CLI output/errors; idempotency; queue persistence; cancellation/resume; managed-owner isolation; immutable evaluators; and rejected client scores. 22 integration tests were deselected in this command.
- 6 real product CAD integrations passed, including the public HTTP/CLI beam walkthrough: thin candidate fails, thicker candidate passes the same suite, STEP downloads and report export succeed. The other two CLI-only tests were deselected by the integration marker.
- The 2 CLI checks were rerun after final malformed-JSON/operation-identity validation fixes and passed.
- Both existing browser workflow checks passed. The bundled UI/docs build and Ruff checks passed.
- A wheel was built and installed into a temporary target. An outside-checkout process verified installed schema/instruction discovery, external initialization, starting/reconnecting to the service, and opening a live external draft with model credentials unset. The test used the existing interpreter's dependency installation and cleaned up its spawned service.
- No paid models, private databases, deployment or archived evidence modifications. Atlas was not live-tested. The existing Starlette/httpx deprecation warning remains nonfatal.

Reproduce from the repository root (Docker CAD/VTOL images must already be built using the documented setup command):

```bash
uv run pytest -m 'not integration' -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py tests/product/test_external_cli.py -m integration -q
npm run build:ui
npm run test:product
.venv/bin/ruff check davinci/product tests/product
uv build --no-build-isolation
uv pip install --reinstall --no-deps --target /tmp/davinci-external-wheel-check dist/da_vinci_harness-0.2.0-py3-none-any.whl
uv run python scripts/check_external_install.py /tmp/davinci-external-wheel-check
```

The installed example can separately be reproduced with `davinci init WORKSPACE --driver external --template custom`, `davinci --workspace WORKSPACE setup --template custom`, `davinci --workspace WORKSPACE service ensure`, then `cd WORKSPACE && python external/walkthrough.py`.

Limits: the gallery still displays the managed v1 workflow; the external route is CLI/API. There is one physical job per experiment at a time and one execution owner per workspace. The beam fixture is a limited linear elastic screen, not general FEA or hardware validation. Multi-file builder plugins, generic mesh generation, automatic scientific validation and an external-agent MCP server remain outside this phase.
