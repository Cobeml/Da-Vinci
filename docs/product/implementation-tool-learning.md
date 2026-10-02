# Tool learning implementation record

Implemented after phases 1–7, 2026-10-01. Core commit: `a6d32ed`. Public contracts and commands: [tested construction helpers](tool-learning.md).

## Decisions and migration

- A separate tool-development aggregate uses the existing workspace worker and execution slot. SQLite and optional Atlas/GridFS remain supported; no database migration, scheduler, extra provider or host CAD dependency was added.
- Reused the older release mechanism's immutable source snapshots, explicit activation decisions, predecessor links and compare-and-set rollback. Archived studies and their release records were not modified. Legacy numeric helpers remain math-only and are not retroactively registered as checked construction tools.
- The first class is a rectangular plate with positioned cylindrical through-holes. The client selects an installed input/output contract and independent analytic/regression recipe before proposing code. Generated source never supplies its own certification. A second sandbox inspects actual STEP without loading the proposed source; every invocation repeats this inspection.
- Promotion requires complete checked evidence. Run pins preserve tool source/dependency/runtime identities independently of the acceptance suite. Rollback withdraws the current version and blocks future use from its pins, while retaining old evidence. Installed-library patches and evaluator changes cannot be applied through tool operations.
- Failures, corrected versions, runtime identity, source and contract artifacts, evidence manifests, promotion/rollback decisions and invocations are projected into project-scoped memory. Physical-design claims remain hypotheses. Imported references cannot activate executable code.
- Managed authoring is an explicit operation using the existing checkpointed/budgeted provider. Automatic request orchestration does not autonomously initiate tool development or promotion. External execution never constructs that provider, including with an ambient key present.

## Demonstrated outcome

| Implementation | Independent result |
| --- | --- |
| Missing translation | Rejected: translated reference bounds and hole locations disagree |
| Corrected transform | Four fixed reference/regression cases pass; registered and explicitly promoted |
| Mirrored hole positions | Rejected despite matching volume and bounds; asymmetric edge locations disagree |
| Compatible later objects | Same pinned helper succeeds; candidate bundles undergo separate evaluation |

Actual runtime: `sha256:7c793165d040ff00df45ffb952e5e590725027565bd9fa55011054f257cc1111`, the repository CAD image with CadQuery 2.8.0. The preserved native test workspace is `runtime/tool-validation/`; `tool-evidence.json` and its `.davinci` ledger/artifacts contain source, contract, actual reference STEP, independent measurements, logs and manifests. Its experiment setup uses deterministic fixtures; the helper construction and inspection evidence is native CAD. It should not be treated as a structural design study.

The separate fresh-wheel walkthrough used native CAD for reference fixtures, tool construction/inspection and final mass evaluation on two objects. Both met the frozen 12 g nominal mass limit. This demonstrates helper correctness for observed inputs and independent mass measurement, not an improvement in structural performance or real-world certification.

## Checks actually run

- `uv run pytest -m 'not integration' -q`: **168 passed**, 40 deselected. Includes ten tool tests covering managed fixtures, keyless/provider isolation, order, idempotency, ownership, incompatible contracts/runtime, cancellation, restart, quota failure, rollback, immutable pins and acceptance-input protection.
- `DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_tool_learning.py -m integration -q`: **1 native helper scenario passed**; actual CAD independently inspected across defective, corrected, misleading and reused versions.
- `uv run python scripts/required_native.py`: **12 passed**, one opt-in live-model test skipped, 51 deselected. The new helper scenario is now a required executed test in this gate.
- Fresh wheel installed into `/tmp/davinci-tools-wheel`, run from `/tmp`: `scripts/check_installed_tools.py` passed with no host CadQuery or model/database credentials. It checked installed schemas, CLI discovery/status/wait/bundle operations, public HTTP learning and two independently evaluated nominal-mass reports.
- Ruff and `git diff --check` passed. Existing Starlette/httpx deprecation warning remains. No browser UI change or browser test run; no paid model, embedding, Atlas/private database or physical hardware test. Phase-7 structural physics was not rerun because its implementation and suite identity did not change.

## Reproduction

Complete installed external example:

```bash
davinci init tool-workspace --driver external --template custom
cd tool-workspace
davinci setup --template custom
davinci service ensure
python -m davinci.product.tool_walkthrough --workspace . --report tool-report.json
```

Deterministic managed authoring through the same service:

```bash
uv run pytest tests/product/test_tool_learning.py -k managed_tool_author -q
```

Wheel reproduction from the checkout, after `davinci setup --template custom`:

```bash
npm run build:ui
uv build --no-build-isolation --out-dir /tmp/davinci-tools-dist
uv venv /tmp/davinci-tools-wheel
uv pip install --python /tmp/davinci-tools-wheel/bin/python /tmp/davinci-tools-dist/da_vinci_harness-0.2.0-py3-none-any.whl
cd /tmp
/tmp/davinci-tools-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_tools.py
```

Use a fresh environment for the wheel check. The helper grammar intentionally excludes general CAD library access, arbitrary dependencies and arbitrary tool classes. Finite tests are evidence, not a proof for every possible implementation/input; the output checks run again at invocation. The complete workflow and all limitations are documented in the public guide.
