# Implementation record: simulation adapters (Prompt 3)

Implemented on 2026-10-01, building on the lifecycle/external-agent phases.

- Kept `Engine.lifecycle`, the local workspace worker, existing runner, storage and artifact abstractions. No second engine, migrations, cloud provisioning or provider calls for simulation operations.
- Added versioned simulation declarations, scoped descriptors and an offline/HTTP catalog. Legacy sensor/gripper/VTOL formulas and exact-unit semantics remain unchanged. Legacy custom scope is explicitly task-declared. V2 authored screening is limited to mass/geometry/linear static and linear isotropic materials.
- Added experiment-specific capability reports: physics, material/fidelity, software versions in pinned runtime, host/cgroup/Docker capacity and uncertain resource estimates. Runtime execution remains local Docker/CPU. Unsupported remote/GPU requests fail explicitly.
- Added dimensional validation, explicit CAD-mm to solver-length STEP conversion, and independent planar-face binding by location, normal, extent and expected count. Candidate hints/labels and evaluator booleans cannot override the structured binding.
- Bounded execution time, allocated CPU budget, memory, files, logs and aggregate output; retained available outputs/logs/resources on failures. Cancellation/restart fencing stays in the shared lifecycle. Peak memory is not claimed as measured; aggregate disk quotas are polled, with bounded collection.
- Added typed hash/provenance manifests for evaluations and verification/reference evidence. Local/GridFS ingestion and HTTP retrieval use bounded streams, checksum verification and safe content delivery. The runner still gathers a bounded bundle in memory; no multi-gigabyte solver pipeline is claimed.
- Final decisions require prescribed required tests, final-stage coverage of critical requirements and complete evidence. Finalization verifies hashes/manifests without silently rerunning tests. Targets remain optional. Prior v1/v2 evidence is never upgraded; old frozen execution identities require linked revisions.
- Updated packaged external beam example, instructions, schemas, managed-author context and CI. Existing custom/YAML/gallery routes remain supported; studies and archived geometry/evidence are unchanged.

Public contracts, migration behavior, reproduction commands and remaining limits are in [simulation-adapters.md](simulation-adapters.md). Test results and installation checks are recorded below after validation.

## Validation completed

- `uv run pytest -m 'not integration' -q`: **115 passed, 25 deselected**. Provider-forbidden external tests ran with absent/dummy credentials; no paid calls or private databases were used. After the final zero-RAM regression, `python -m pytest tests/product/test_simulation.py -m 'not integration' -q` passed **20 tests**.
- `DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py tests/product/test_external_cli.py tests/product/test_simulation.py -m integration -q`: **9 passed, 22 deselected**, using the installed local CAD and VTOL Docker images. Existing sensor/gripper/VTOL/custom baselines, native analytic references, public CLI workflow and both lifecycle drivers passed. A prior attempt correctly refused a mid-run harness source edit; the suite passed after the implementation was held stable.
- `DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_simulation.py -m integration -q`: **3 passed, 20 deselected** after adding native coincident-face ambiguity and cancellation with partial-output preservation.
- `npm run test:product`: **2 browser tests passed**, including interactive geometry via the streaming artifact endpoint and existing localhost protections.
- `.venv/bin/ruff check davinci/product davinci/runner.py davinci/artifacts.py tests/product scripts/check_external_install.py` and `git diff --check`: passed.
- `node scripts/build_product_ui.mjs` refreshed bundled documentation using the existing compiled UI. `.venv/bin/python -m build --wheel --no-isolation --outdir /tmp/davinci-simulation-dist` built the wheel.
- `uv pip install --reinstall --no-deps --target /tmp/davinci-simulation-wheel-check /tmp/davinci-simulation-dist/da_vinci_harness-0.2.0-py3-none-any.whl`, then `.venv/bin/python scripts/check_external_install.py /tmp/davinci-simulation-wheel-check`: passed schemas, adapter discovery, instructions, localhost service start/reconnect and keyless external experiment creation. This isolated package installation reused the interpreter's installed dependencies; it was not a new dependency-resolution test. A separate import-blocking check verified wheel catalog/schema discovery with CadQuery/OCP/NumPy/SciPy/AeroSandbox imports forbidden. CI also exercises wheel installation into a fresh environment.

Not run: private Atlas/GridFS, paid model generation, remote/GPU execution, or nonlinear/contact/dynamics/flight validation. Remote/GPU executors and broader physics are not implemented. The existing Starlette/httpx deprecation warning remains unrelated to this phase. No archived studies or stored historical evidence were edited.
