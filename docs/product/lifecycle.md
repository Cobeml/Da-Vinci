# Experiment lifecycle, version 2

The Python service `Engine.lifecycle` and localhost `/api/v2` endpoints support test-first engineering experiments. An experiment can open with just an object, description, driver, actor, and operation ID. It needs no builder, baseline, finalized parameters, model key, or cloud database.

The [external-agent CLI and asynchronous HTTP route](external-agents.md) now build on this lifecycle foundation. The existing gallery and YAML worker still use the explicit v1 compatibility adapter. V2 experiments are available through the public CLI/HTTP operations and the installed gallery. The object view displays assumptions, coverage, capabilities, iterations, final evidence and driver ownership. Archived studies are unchanged.

## Driver and ownership boundary

`driver` is `external` or `managed`; `mode` is independently `live` or `replay`.

- **External:** the coding agent supplies reasoning, requirements, evaluator code, reference expectations, candidate code, and reflections. Da Vinci validates transitions, runs isolated execution, checks evidence, stores artifacts, and retrieves experience. No provider is instantiated for these operations.
- **Managed:** `Engine.managed.advance(id, command, stage)` supplies built-in reasoning for `author`, `propose`, or `reflect`, then applies the answer through the same lifecycle service. Provider requests retain spending reservations, request checkpoints, and uncertain-output handling. A client can chain routine lifecycle operations without confirmation prompts. The existing v1 managed loop remains available through YAML.

The managed author receives the contract schemas and retrieved experience. It must mark missing critical requirements `resolved: false`; these become `pending_input` and put the experiment in `awaiting_input`. The user or calling agent updates the draft with the missing engineering information. Arbitrary task authoring is not proof that a physical test is appropriate: the caller must supply reference fixtures and independent expected values before freezing. This phase does not add an autonomous fixture-authoring loop or a v2 browser wizard.

The `actor` is a persistent local ownership label, not an authentication credential. A different actor cannot advance the experiment, and the driver is fixed at opening. Every mutation includes the current `revision` and a unique `operation_id`. Compare-and-set updates atomically commit the state, operation receipt, and history in one run document. Competing submissions from separate SQLite connections cannot both advance an iteration. Atlas uses the same single-document CAS.

A repeated operation ID with identical arguments returns current state without re-execution; different arguments conflict. A stale revision or invalid transition returns HTTP 409. A receipt can describe a started or interrupted execution, so inspect `phase` and `job`, not just the HTTP response. Jobs, proposals, and verification records are retained in the run aggregate; source, geometry, logs, and other large evidence use the existing artifact store. The ledger is bounded at 8 MB and 500 commands: open a linked experiment when needed.

One execution owns the workspace slot at a time, shared with the v1 worker. Verification, physical evaluation, and managed reasoning claim it before executing. The server remains loopback-only, with its existing host/origin and JSON-write protections. Run one server per workspace/database. Direct Python callers must observe that same deployment boundary; `recover()` is exclusively a server-startup operation, not a way to steal a live job.

## State order

```text
open → draft ⇄ awaiting_input
         │
         ├─ inspect/import reference STEP; verify tests; inspect capabilities
         │
         └─ freeze → frozen → candidate_submitted → evaluating → evaluated
                                                                  │
                                                               reflect
                                                                  ↓
                                                              reflected
                                                              /       \
                                                    next candidate   finalize
                                                                       ↓
                                                                    completed
```

No new candidate may be submitted or requested from the managed proposer before freeze. Imported reference STEP files are labeled `reference_only`; they never become accepted candidates. External inspection and reference-fixture creation are allowed before freeze. Verification executes the reference STEP against the draft evaluator, without executing candidate code.

A frozen plan cannot be edited. `revise()` opens a linked draft and copies only the plan/evaluator/runtime definitions. It copies no passing results, capability checks, or candidates. After a correction, reverify the tests and resubmit affected candidate sources for fresh evaluation. Historical evidence retains its original meaning; no database migration or rewriting of archived results occurs.

`cancel` fences results and stops the active sandbox through the existing cancellation callback. Completed evidence is retained. On server restart, active jobs become `interrupted`; the old job token can no longer commit a result. Explicit `resume` restores the previous safe phase. An interrupted physical evaluation requires a new evaluation operation ID; an uncertain model request blocks resume and requires a linked experiment. Model requests already submitted can incur cost even if cancelled. No automatic retry is performed.

## Public contracts

Pydantic models are in `davinci/product/contracts.py`. Use `Class.model_json_schema()` for machine-readable schemas. Contract `version` is 2. Unknown fields are rejected; `metadata` is a descriptive extension map and cannot change acceptance behavior. Numbers must be finite.

| Contract | Required meaning |
|---|---|
| `OpenExperiment` | Object, description, external/managed driver, live/replay mode, actor, operation ID; optional parent and budget |
| `Requirement`, `Assumption`, `Material` | Critical/resolved requirements, sources, dimensions/units, assumption applicability, material property provenance |
| `Plan`, `Test`, `Coverage` | Requirement-to-test mapping, required/advisory tests, fixed inputs, load cases, boundary conditions, declared metric units, hard criteria, applicability, numerical error and uncertainty limits |
| `Interface` | Semantic ID, independently checked binding rule, unit and tolerance |
| `Evaluator` | Trusted `evaluate.py` and explicit support resources, with provenance; no builder |
| `Runtime` | Immutable Docker `sha256:` image ID, solver identification/provenance, timeout and memory bounds |
| `Verification`, `CapabilityReport` | Reference STEP, independently supplied expectations/tolerances, actual execution evidence, verified/unavailable/unverified status |
| `Candidate` | Title, change, builder source, editable parameters; no evaluator or acceptance fields |
| `SimulationJob`, `TestResult`, `EvaluationResult` | Execution owner/operation, identities, typed status/reason, measurements and accuracy, independently checked bindings, artifacts and decisions |
| `ExperienceReference` | Hypothesis or linked observation, candidate/result references, explicit `transfers_acceptance: false` |

`Plan.design_schema` is a closed JSON Schema object with a unit for each editable variable (`1` for dimensionless quantities). `Test.fixed_inputs`, loads, material properties, and acceptance limits are separate. Evaluators receive the frozen physical inputs and STEP geometry, never the candidate's editable parameter claims. Schema references may use local JSON pointers only; remote resource resolution and `$id` rebasing are rejected. Unit strings must match exactly; automatic unit conversion is not included.

Each metric needs an accuracy method, maximum absolute numerical error, and maximum absolute uncertainty, all in that metric's declared unit. The evaluator must report both error estimates. The host rejects missing/excessive estimates. Hard limits use conservative measurement bounds: for an upper limit, `value + uncertainty + numerical_error <= limit`; lower limits use the opposite bound.

An objective target is advisory and remains separate from hard criteria. A design can pass its hard limits while missing its target. `objective_target_attained` is null when no target or usable measurement exists. It never makes incomplete evidence acceptable.

## Evaluator and builder interfaces

A candidate defines `build(parameters, interfaces)` and exports a CadQuery/OCP-compatible assembly through the existing sandbox build entrypoint. V2 `interfaces` is the list of semantic interface definitions. Builders receive no evaluator resources. The harness forwards only the exported STEP to the evaluator; a builder-written `result.json` is ignored.

The frozen evaluator defines:

```python
def evaluate(step_path, request):
    # request contains test, materials, interfaces, and assumptions.
    # Import and measure STEP; validate the declared geometry/binding/mesh rules.
    return {
        "test_id": request["test"]["id"],
        "status": "pass",
        "reason": "ok",
        "applicable": True,
        "mesh_valid": True,
        "bindings": {"mounting_interface": True},
        "metrics": {
            "mass_g": {
                "value": 12.0, "unit": "g",
                "numerical_error": 0.001, "uncertainty": 0.1,
            }
        },
    }
```

This illustrates the return protocol, not a valid physical evaluator by itself. Each declared interface requires a true binding check. A rule may generate geometry-dependent meshes/bindings after freeze, but the rule and its independent checks must already be declared. There is no generic mesher or automatic semantic face selector in this phase.

Verification needs at least one passing and one physically failing reference per test, with expected values for every declared metric. Both must agree with the frozen criteria, expected status, and reference tolerances. Failed verification remains visible and blocks a validated freeze for that plan version. Changing the plan/evaluator/runtime invalidates previous verification matches. A test can be marked unavailable only through an actual execution reporting unsupported capability; there is no client endpoint to upload a trusted passing result.

With known unavailable tests, `freeze(draft_only=True)` allows labeled exploratory work, provided critical requirements are resolved and have declared coverage. Skipped/unverified tests alone do not permit this exception. A draft-only suite stays ineligible for acceptance even if a later runtime happens to produce passing measurements; open and verify a linked version to remove that restriction.

Task-author evaluators are trusted to measure their declared physics correctly, but run in the sandbox too. Reference checks and typed contracts catch setup and regression errors; they cannot prove an arbitrary evaluator scientifically adequate. Uncertainty estimates remain part of the evaluator's documented methodology.

## Identities and outcomes

- `plan_id`: requirements, physical inputs, tests, criteria, objectives and editable-variable schema.
- `evaluator_id`: evaluator resource content and provenance, independent of the candidate builder.
- `runtime_id`: pinned solver/image and resource configuration.
- `execution_id`: archived host scoring/contracts/lifecycle, sandbox runner, and build wrapper source. A changed implementation requires a linked version and re-verification before new evidence is produced.
- `suite_id`: the frozen identities, verification capability evidence, and draft eligibility.
- `candidate_version`: candidate source and parameters, independent of the suite.

Changing builder source or design parameters leaves the suite identity unchanged. Results retain these identities, source artifact and Git commit references, geometry checksums, evaluator outputs, logs, durations, and the simulation job owner/operation. Plan revisions and the final report are content-addressed artifacts. Finalization verifies artifact checksums and recomputes decisions from recorded test evidence; it does not automatically run a more expensive convergence campaign. Declare such checks as required tests when needed.

| Test status | Meaning |
|---|---|
| `pass` | Declared checks, evidence, accuracy and hard limits passed |
| `physical_failure` | Valid evidence demonstrates an unmet physical limit |
| `invalid_setup` | Build, binding, units or evaluator output is invalid |
| `numerical_failure` | Solver failure or unmet numerical/uncertainty requirements |
| `not_run` | Missing evidence, interruption, timeout, cancellation or resource exhaustion |
| `unsupported_capability` | Required runtime or physics is unavailable/inapplicable |

Reason codes retain distinctions such as `build_failed`, `timeout`, `cancelled`, `resource_exhaustion`, `invalid_binding`, `missing_evidence`, and `unsupported_physics`. Interrupted jobs retain an `interrupted` reason without inventing a completed result. Required tests must all have complete pass/failure evidence for `evidence_complete`, and all must pass for `design_accepted`. `execution_completed`, `evidence_complete`, `design_accepted`, and `objective_target_attained` are separate fields. Finishing a report does not imply an accepted design.

External reflections remain hypotheses even with result links. For managed reflections, a linked observation identifies its evidence; it is not proof of every claim in the prose. Retrieval can return cross-task lessons and v1 hypotheses, but never transfers a passing score. Retrieval is local lexical ranking by default and also works against Atlas documents without embeddings. Managed v1 vector retrieval now requires explicit `embeddings: true` and a configured key. No embedding request is made simply because a database or credentials exist.

## Python and HTTP use

Open a local draft without consulting `.env` or any model service:

```python
from pathlib import Path
from davinci.config import Settings
from davinci.product.engine import Engine
from davinci.product.contracts import OpenExperiment, Command

engine = Engine(Path("my-workspace"), credentials=Settings(
    _env_file=None, openai_api_key="", mongodb_uri=""))
life = engine.lifecycle
row = life.open(OpenExperiment(
    object={"slug": "beam", "name": "Cantilever beam"},
    description="Reduce mass under a specified tip load",
    driver="external", mode="live", actor="coding-agent", operation_id="open-1"))

def command(operation):
    return Command(actor=row["actor"], revision=row["revision"], operation_id=operation)

# row = life.update_plan(row['_id'], command('plan-1'), plan, evaluator, runtime)
# row = life.fixture(row['_id'], command('fixture-1'), step=step_bytes, provenance='...')
# row = life.verify(row['_id'], command('verify-1'), verification)
# reports = life.capabilities(row['_id'])
# row = life.freeze(row['_id'], command('freeze-1'))
# row = life.submit_candidate(row['_id'], command('candidate-1'), candidate)
# row = life.request_evaluation(row['_id'], command('evaluate-1'))
# row = life.reflect(row['_id'], command('reflect-1'), lesson='...', result_id=row['results'][-1]['id'])
# row = life.finalize(row['_id'], command('report-1'))
```

The complete executable reference is `tests/product/test_cad.py::test_v2_reference_verification_and_independent_beam_solver`, with task/provider fixtures in `tests/product/test_lifecycle.py`. It builds real reference solids, verifies a linear beam stiffness solver, rejects a thinner failing part, ignores forged builder results, and archives a final report without a model key.

Start `davinci serve` to use the same service over HTTP. `POST /api/v2/experiments` accepts `OpenExperiment`. For `/api/v2/experiments/{id}`, the mutation paths and additional body fields are:

| Path | Fields beyond `actor`, `revision`, `operation_id` |
|---|---|
| `/plan` | `plan`, `evaluator`, `runtime` |
| `/fixtures` | `step_base64`, `provenance` |
| `/verify` | `verification` |
| `/freeze` | `draft_only` (defaults false) |
| `/candidates` | `candidate` |
| `/evaluate` | None; results can only be created by execution |
| `/reflections` | `lesson`, optional `result_id` |
| `/finalize`, `/cancel`, `/resume` | None |
| `/managed/author`, `/managed/propose`, `/managed/reflect` | None; requires a managed experiment |

`POST /revisions` accepts a new `OpenExperiment` whose `parent_experiment_id` is the old ID. GET routes provide experiment list/detail, `/capabilities`, and `/api/v2/experience?q=...`. Artifacts use the existing `/api/v1/artifacts/{id}` route. HTTP verification and evaluation now return 202 queued jobs; poll `/jobs/{job_id}` and retrieve `/results`. The Python service methods remain synchronous for in-process adapters. External agents should use the service-backed CLI or HTTP route and reuse their operation ID after a disconnected request. OpenAPI schemas are available through `/openapi.json`.

Managed v2 replay in automated tests uses an injected deterministic provider fixture. The built-in replay proposals remain specific to v1 templates; v2 does not invent a generic deterministic engineering author. There were no paid-provider or private-Atlas calls in this phase's validation.

## Compatibility and migration

Version-1 YAML, existing `/api/v1` routes, and gallery data shapes remain supported. The managed loop delegates candidate archival, physical evaluation, and reflection persistence to `LegacyAdapter`; its original screening and VTOL retention rules remain intact. New v1 runs explicitly record `driver: managed`, mode, and separate informational acceptance identities.

Existing v1 records are interpreted through a read-only adapter with `guarantees: legacy-unverified-coverage` and `test_first_verified: false`. They are not backfilled or certified against v2 coverage. Legacy lessons are retrieved as hypotheses. A historical passing score can never supply v2 reference verification or design acceptance. There is no schema migration, new storage backend, scheduler, hosted service, or required second model provider.

## Simulation adapter extension

[Simulation adapters and evidence](simulation-adapters.md) adds explicit test scope/fidelity, dimensional conversions, independent planar-region selection, resource admission checks, job budgets and typed manifests beneath the same lifecycle. Frozen execution identities include this implementation. Existing records remain unchanged; linked revisions are required to rerun an old frozen experiment with new execution code. A preliminary screen cannot cover a required final test. Finalization verifies retained final evidence separately from targets and search termination.
