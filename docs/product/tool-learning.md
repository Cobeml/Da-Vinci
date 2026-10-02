# Tested construction helpers

Da Vinci can develop a reusable CAD helper through the same localhost service used by external and managed agents. Tool development has its own contract, version history, checks and promotion policy. It does not change a design's evaluator or acceptance suite.

The initial additional class is `perforated_plate_v1`: construct one rectangular plate with separated circular Z through-holes, then translate it. It handles asymmetric patterns, fractional dimensions and off-origin parts. This is a construction utility, not a structural solver or a generic arbitrary-Python plugin. Existing objective-change tools retain their math-only restrictions and legacy records.

## Workflow and public contract

1. Record a repeated need or suspected defect, its observations and originating experiment. These observations are author claims.
2. Select the class's versioned input/output contract, applicability and an immutable local runtime image. The class's established analytical checks and regression cases are fixed before implementation is proposed. Clients cannot replace them with generated tests.
3. Propose source and optionally link its predecessor. Source, SHA-256, dependency identity, contract, runtime and source Git commit are preserved even for rejected implementations.
4. Queue independent checks. The existing workspace worker builds reference outputs in an isolated container, then imports the STEP into another isolated container that never receives the helper source. Host code compares measurements against established expectations.
5. Explicitly promote a tested version. The policy requires every independent check and complete archived evidence; passing a caller-supplied flag has no effect.
6. Pin the promoted version to a frozen experiment, invoke it with dimensionally validated arguments, and inspect its evidence. Every invocation repeats independent output checks. Download a normal builder/parameter candidate bundle and submit it through the ordinary lifecycle for independent design evaluation.
7. Promote a new checked version for future pins, or roll back to a previous tested promotion with a reason. Rollback withdraws the current version: runs pinned to it cannot invoke it again. Older evidence remains unchanged. Existing runs never silently switch versions.

The input schema is `PlateArguments`: `unit="mm"`, `length`, `width`, `thickness`, `radius`, `holes` as XY pairs, and `translation` as XYZ. XY dimensions are 5–500 mm, thickness 0.5–50 mm, radius 0.25–20 mm, one to twelve holes, and translation within ±1000 mm. Holes need at least 0.25 mm clearance from each other and the plate edge. The plate is centered in XY and starts at Z=0 before translation. The output is a CadQuery Workplane exported to STEP by a trusted wrapper. The class catalog and installed JSON schemas document these limits.

The tested runtime is the repository's CAD image, **CadQuery 2.8.0 / OCP 7.9.3.1.1**, resolved to its immutable Docker image ID. No host CadQuery dependency is needed. Missing or incompatible runtimes fail; no alternate CAD kernel or physical model is substituted.

## Independent checks and capability boundary

Four predeclared reference patterns test origin-centered and translated plates, asymmetric holes, fractional dimensions and a thicker multi-hole part. Expected volume is `L*W*t − n*pi*r²*t`. Independent inspection checks valid single-solid topology, volume, all six bounds, and the centers/radii of circular edges at both plate surfaces. Relative volume tolerance is 1e-7 with a 1e-7 mm³ absolute floor; geometric tolerance is 1e-6 mm. These tolerances accommodate STEP numerical round trips for the documented dimensions, not manufacturing error. A mirrored-hole implementation has the right volume and bounds but fails the edge-location checks.

The source capability allowlist permits one plain `run(arguments)` function, `cadquery as cq` and `math` imports, small numeric/list operations and these construction operations: `Workplane`, `box`, `pushPoints`, `circle`, `extrude`, `cut`, `translate`, `union`. It excludes exporters, filesystem/network/process access, introspection and arbitrary dependencies. The allowlist supplements the existing non-root, network-disabled, read-only Docker boundary; it is not a replacement for it. The helper receives arguments only. Frozen plans, evaluator code, reference expectations and trusted results are not mounted in its sandbox.

Checks provide evidence for this construction class and the observed inputs; finite tests do not prove arbitrary code correct for all inputs. Each invocation is inspected again. Tool results cannot provide physics scores or confer acceptance. Proposed source cannot write the installed package. Library/evaluator corrections remain ordinary reviewable repository patches with reproducible tests; evaluator corrections require linked suite revisions and fresh evaluation evidence.

## Operations

All mutations use `actor`, `revision` and `operation_id`, except opening, which has no revision yet. Tool revision numbers are separate from experiment revision numbers. Repeating an operation with the same payload reuses it; changing the payload under the same ID fails with HTTP 409. Only the development owner may define, propose or promote. Another experiment owner may discover, pin and invoke a compatible tested version in the same workspace/project.

| CLI | HTTP | Contract / purpose |
| --- | --- | --- |
| `davinci tools classes` | GET `/api/v2/tools/classes` | Supported capabilities, schemas and independent reference recipe |
| `davinci tools list` | GET `/api/v2/tools` | Project-scoped development catalog |
| `davinci tools open --file need.json` | POST `/api/v2/tools` | `ToolNeed` |
| `davinci tools status ID` | GET `/api/v2/tools/ID` | Versions, jobs, checks, policy decisions, evidence |
| `davinci tools define ID --file definition.json` | POST `/api/v2/tools/ID/define` | `ToolDefinition` |
| `davinci tools propose ID --file proposal.json` | POST `/api/v2/tools/ID/propose` | `ToolProposal` |
| `davinci tools check ID --file check.json` | POST `/api/v2/tools/ID/check` | `ToolVersionCommand`; returns queued job |
| `davinci tools wait ID --timeout 180` | Poll GET `/api/v2/tools/ID` | Wait without a blocking evaluation HTTP request |
| `davinci tools promote ID --file decision.json` | POST `/api/v2/tools/ID/promote` | `ToolPromotion`; reason required |
| `davinci tools rollback ID --file decision.json` | POST `/api/v2/tools/ID/rollback` | `ToolPromotion`; version is the current version to withdraw |
| `davinci tools pin EXPERIMENT --file pin.json` | POST `/api/v2/experiments/EXPERIMENT/tool-pins` | `ToolPin`; **experiment** revision |
| `davinci tools invoke ID --file invocation.json` | POST `/api/v2/tools/ID/invoke` | `ToolInvocation`; **tool** revision, target experiment and arguments |
| `davinci tools cancel ID --file command.json` | POST `/api/v2/tools/ID/cancel` | `Command`; job or development owner |
| `davinci tools bundle ID JOB --output candidate.json` | GET `/api/v2/tools/ID/bundles/JOB` | Reviewed source/parameter bundle, construction provenance, no scores |
| `davinci tools generate EXPERIMENT --file generation.json` | POST `/api/v2/experiments/EXPERIMENT/tool-proposals` | `ManagedToolProposal`; explicit managed reasoning request |

`davinci external schemas` and GET `/api/v2/schemas` expose every contract. CLI output uses the existing JSON envelope and exit codes: 0 completed operation (inspect `passed` separately), 2 invalid input, 3 unavailable service, 4 conflict, 5 missing record, 6 interrupted/cancelled wait, 7 timed-out wait. Use `davinci external artifact ARTIFACT_ID --output PATH` for evidence downloads.

Example definition body (replace the image ID with the service's resolved image):

```json
{
  "actor": "coding-agent", "revision": 0, "operation_id": "define-1",
  "tool_class": "perforated_plate_v1",
  "applicability": "Rectangular plates with separated round through-holes; construction only",
  "runtime": {
    "image": "sha256:<resolved-image-id>", "solver": "CadQuery construction",
    "provenance": "Local repository CAD image",
    "memory_gb": 2, "cpu_cores": 1, "timeout_seconds": 60,
    "job_seconds": 120, "compute_seconds": 120,
    "artifact_bytes": 16000000, "file_bytes": 8000000
  }
}
```

The runtime is bounded to at most 4 GB RAM, 2 CPUs, 300 wall seconds, 600 compute seconds and 64 MB artifacts per job. A development has a conservative 1800 compute-second reservation budget and at most twenty versions. Interruptions retain reservations. Source/dependency changes need a new version; contract/checker/runtime changes need a new development and verification. No automatic paid retries, cloud provisioning or package installation occurs.

On restart, queued/running tool jobs become interrupted. Resubmit `check` or `invoke` explicitly with a fresh operation ID and current revision; completed receipts remain reusable. Cancellation fences late registration. Failed/interrupted checks cannot promote a version. A failed evidence commit becomes interrupted and cannot claim successful validation.

## External and managed use

External tools never construct the generation provider or request embeddings. The service uses SQLite/local artifacts by default; optional Atlas/GridFS uses the same collections/artifact abstraction. A generation key in the environment does not enable tool reasoning.

Managed reasoning can explicitly author a proposal using `tools generate` on a manually driven managed experiment, after a tool contract is defined. It uses the existing provider's request checkpoints and run budget. A deterministic provider can exercise this path without a paid call. The automatic natural-language loop can retrieve tested tool references; it does not yet autonomously initiate the entire tool-development process or pause itself to ask for promotion. Both drivers use the same public checking, promotion, pinning and invocation services.

The run stores immutable `tool_pins`, including version, runtime, dependency/source hashes and suite identity. A copied builder bundle is self-contained; promoting a tool cannot change its source. To change a pinned helper, open a new experiment or continuation and explicitly select the version. Tool runtime identity is independent of the design solver runtime; both are preserved and design evaluation always uses the frozen suite's runtime.

Memory stores tool references with source/contract artifacts, hashes, predecessors, outcomes and execution manifests. Failures and promotion/rollback decisions remain searchable. Construction observations are harness-observed, while physical-design claims stay hypotheses. Imported memory never activates executable tools. A retrieved reference must pass current registry, scope, contract, version and artifact checks before use; old successful checks do not override withdrawal or missing evidence.

## Reproduce the complete example

From an installed package:

```bash
davinci init tool-workspace --driver external --template custom
cd tool-workspace
davinci setup --template custom
davinci service ensure
python -m davinci.product.tool_walkthrough --workspace . --report tool-report.json
```

The example first freezes a geometry-derived mass test using independent positive/negative fixtures. It reproduces a lost-translation defect, rejects it, checks a corrected implementation, rejects a misleading mirrored-hole implementation, promotes and pins the correction, then reuses it on two separately frozen objects. Each candidate is independently evaluated against a 12 g nominal mass limit. This demonstrates construction and mass checking, not structural certification or optimization improvement.

For a different retry after an interrupted demonstration, inspect persisted jobs first and choose a new `--operation` prefix when opening a new demonstration. Routine public operations are individually idempotent; the example is a linear demonstration, not an automatic recovery driver.

From a checkout:

```bash
uv run pytest tests/product/test_tool_learning.py -m 'not integration' -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_tool_learning.py -m integration -q
uv run python scripts/required_native.py
```

The native helper test uses actual CAD construction and independent STEP inspection; its experiment setup is a deterministic lifecycle fixture. The fresh-wheel check in `scripts/check_installed_tools.py` uses real CAD throughout, including reference fixtures and final nominal-mass evaluations. Managed authoring tests use deterministic reasoning and make no physical-validation claim from mocked outputs.

See the [implementation record](implementation-tool-learning.md) for executed checks, preserved local evidence, compatibility decisions and exact wheel reproduction commands.
