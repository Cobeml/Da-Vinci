# External coding agents

An external agent supplies the engineering reasoning, test authoring, candidate source and reflections. Da Vinci validates lifecycle operations, executes isolated CAD and simulation jobs, and retains evidence. It never constructs the generation provider for an external experiment, even if model credentials exist. External `driver` is independent of `mode`; this is not replay with a different label.

Use the supported CLI or localhost HTTP API. The CLI is an HTTP client: it does not open the experiment database or execute a second engine. SQLite and local artifacts are sufficient. Atlas/GridFS remain available through the same explicit workspace configuration; embeddings are neither needed nor called on this route.

## Start a workspace and its service

After installing from source as described in [Quickstart](quickstart.md):

```bash
davinci init beam-workspace --driver external --template custom
cd beam-workspace
davinci doctor --driver external
davinci setup --template custom
davinci service ensure
```

`service ensure` connects to the existing service or starts `davinci serve --no-browser` in the background. It checks a workspace identity on the health endpoint, so an unrelated service on the same port is a conflict. Concurrent starts are serialized; the existing server lock prevents duplicate workspace servers. Output/logs are in `.davinci/service.log`. Use `davinci service status` to reconnect. To manage the process yourself, run `davinci serve --no-browser` in a terminal instead. There is no new distributed scheduler or remote host option.

The default driver is written to `workspace.yaml`. Existing workspaces default to managed. `doctor` reports whether a model key is actually required for the selected driver and does not require a baseline/builder for an external draft. The v1 `run run.yaml` shortcut is rejected in a workspace explicitly configured for external use; use the external commands below. Explicit managed experiments can still coexist in a workspace through their existing API.

External initialization provides:

- `experiment.json`: a draft request to edit, not a finalized engineering design.
- `AGENTS.md`: instructions for the coding agent.
- `external/schemas.json`: JSON Schemas for request, result, job, and CLI contracts.
- `external/plan.json`, `evaluate.py`, `runtime.json`, `build.py`: a nominal beam example.
- `external/walkthrough.py`: an executable public-API example.
- `task/` and `run.yaml`: the unchanged v1 custom starter, retained for compatibility. They are not consumed by the external experiment.

A draft itself only needs the request; delete/replace the example files as appropriate. No builder or baseline is required to open it. External initialization defaults to the existing `sensor` setup target if `--template` is omitted; use `--template custom` for the accompanying custom-task starter.

Schemas and instructions are also discoverable without starting a server:

```bash
davinci external --help
davinci external instructions
davinci external schemas
```

They ship inside the Python package under `davinci.product/resources/external`. HTTP clients can GET `/api/v2/instructions`, `/api/v2/schemas`, and `/openapi.json`. No concrete client requires MCP here, so no MCP dependency or adapter is added.

## Complete walkthrough: request, failed design, revision and evidence

The installed example models a 40 × 20 mm rectangular cantilever, nominal aluminium properties and a fixed 100 N tip force. It solves the free-end beam stiffness equations from measured STEP dimensions. Limits are 100 MPa stress and 0.5 mm deflection. The 1 g mass objective is advisory, not an acceptance threshold. This is a restricted linear elastic screen, with no fatigue, joint, or hardware validation claim.

For an executable end-to-end example, after the setup above run:

```bash
python external/walkthrough.py
```

The script calls only public localhost operations through `davinci.product.client.Client`. It imports no Engine, Store, or private lifecycle methods. It performs the following steps, which a coding agent can also execute with the CLI:

1. **Understand and retrieve.** Edit `experiment.json` with the qualitative request, stable actor and opening operation ID. Retrieve relevant hypotheses, then open the experiment:

   ```bash
   davinci external experience "cantilever beam stiffness"
   davinci external open --file experiment.json
   davinci external status EXPERIMENT_ID
   ```

2. **Define and validate tests before generating candidates.** Edit requirements, fixed inputs, material provenance, load cases, interfaces, accuracy, criteria and design variables in `external/plan.json`. Mark missing critical requirements unresolved. The full plan update contains both requirements and tests. The `--task` loader reads `plan.json`, `runtime.json`, `evaluate.py` and optional explicit filenames in `resources.json`; it never walks arbitrary directories. The server resolves the installed Docker image to its immutable ID.

   ```bash
   davinci external plan EXPERIMENT_ID --task external --image da-vinci-cad:local --operation-id plan-1
   davinci external validate-plan EXPERIMENT_ID
   ```

   For fully specified JSON inputs instead, use `--file plan-bundle.json` containing `plan`, `evaluator` and `runtime`, matching `PlanCommand` minus the command identity fields. `--task` and `--file` are mutually exclusive. Fixed acceptance inputs never come from the editable candidate parameters.

3. **Verify reference fixtures.** Explicitly labeled reference work is allowed before freezing:

   ```bash
   davinci external reference-build EXPERIMENT_ID --source external/build.py --parameters external/revised-parameters.json --title "Passing reference" --provenance "Closed-form rectangular beam reference" --operation-id reference-pass
   davinci external wait EXPERIMENT_ID JOB_ID --timeout 300
   ```

   Repeat with `external/failed-parameters.json` and a different operation ID to build the failing reference. The finished job returns `fixture_artifacts`. Existing STEP can instead be imported with `external fixture ID --step reference.step --provenance "..." --operation-id upload-1`.

   Write a verification JSON file with test ID, reference artifact, expected status, expected measurements, exact units, tolerances, and provenance. Every test needs independent positive and negative references. For the 4 mm reference, expected mass is 8.64 g, stress 75 MPa, and deflection 0.2857142857 mm. For the 2 mm reference, they are 4.32 g, 300 MPa, and 2.2857142857 mm. The example script shows the complete `Verification` payload; these values are derived independently of the evaluator output.

   ```bash
   davinci external verify EXPERIMENT_ID --file verification-pass.json --operation-id verify-pass
   davinci external wait EXPERIMENT_ID JOB_ID
   davinci external verify EXPERIMENT_ID --file verification-fail.json --operation-id verify-fail
   davinci external wait EXPERIMENT_ID JOB_ID
   davinci external capabilities EXPERIMENT_ID
   davinci external validate-plan EXPERIMENT_ID
   davinci external freeze EXPERIMENT_ID --operation-id freeze-1
   ```

   Only freeze once readiness/verification supports it. `--draft-only` is reserved for recorded unavailable capabilities; it never authorizes acceptance or skips unresolved critical requirements.

4. **Submit and evaluate the failing candidate.** Reference fixtures are not automatically candidates. Submit the source/parameters explicitly under the frozen suite:

   ```bash
   davinci external submit EXPERIMENT_ID --source external/build.py --parameters external/failed-parameters.json --title "Thin beam" --operation-id candidate-1
   davinci external evaluate EXPERIMENT_ID --operation-id evaluation-1
   davinci external wait EXPERIMENT_ID JOB_ID
   davinci external results EXPERIMENT_ID
   davinci external artifact ARTIFACT_ID --output thin-beam.step
   ```

   Expect `physical_failure`, complete measured evidence, and `design_accepted: false`. Job completion alone does not indicate feasibility. The measured STEP, logs, test outcomes and source identities are available for diagnosis.

5. **Reflect and revise the geometry.** Write `reflection.json`, for example:

   ```json
   {"lesson":"The thin beam exceeds the frozen stress and deflection limits; test a thicker section.","result_id":"RESULT_ID"}
   ```

   ```bash
   davinci external reflect EXPERIMENT_ID --file reflection.json --operation-id reflection-1
   davinci external submit EXPERIMENT_ID --source external/build.py --parameters external/revised-parameters.json --title "Thicker beam" --operation-id candidate-2
   davinci external evaluate EXPERIMENT_ID --operation-id evaluation-2
   davinci external wait EXPERIMENT_ID JOB_ID
   davinci external results EXPERIMENT_ID
   ```

   The 4 mm design should pass this screen under the same suite hash. The optional 1 g target remains unmet. Submit a second reflection recording those limits. Externally written reflections remain `hypothesis` even when linked to evidence; a link is not independent verification of the prose.

6. **Final checks and export.**

   ```bash
   davinci external finalize EXPERIMENT_ID --operation-id final-1
   davinci external report EXPERIMENT_ID --output report.json
   ```

   The export includes plan/evaluator/runtime identities, operation and job history, candidate provenance, test results, verification and reflection records, and artifact references. STEP/log bytes are downloaded separately. Artifact downloads verify their content hash. The example saves both candidate STEP files and its report in `external/`.

If the **evaluator**, load cases or thresholds need correction, use `external revise ID --file next-experiment.json`, where the new `OpenExperiment` has a fresh operation ID and `parent_experiment_id` set to the original. This copies only definitions into a draft. Verify again and reevaluate affected source; never copy a passing score or edit the original frozen suite. A builder edit alone needs only a new candidate after reflection.

## Candidate bundle and provenance

`--source` is one UTF-8 Python file, at most 40,000 characters. `--parameters` is a JSON object matching the frozen closed design schema. `build(parameters, interfaces)` returns a CadQuery Assembly in millimetres; v2 `interfaces` is the semantic-interface list in the plan. Libraries must be available in the pinned sandbox image. Multiple builder support files are not uploaded implicitly. The separate evaluator can have explicit support resources.

The HTTP equivalent is `CandidateCommand` with `candidate: {title, change, source, parameters, metadata}`. `metadata` is descriptive only. CLI submissions record source/parameter filenames, and the service records actor, operation ID, source content hash/artifact, Git snapshot commit, candidate version, and suite ID. Client scores, accepted flags, evaluator changes, or acceptance limits are not permitted fields. A builder-written result file is never forwarded to the independent evaluator.

## JSON output, jobs, errors and retries

New CLI operations output one JSON object: `{"version":2,"ok":true,"data":...}`. `--help` is human-readable text. Status includes `phase`, `revision`, `pending_input` and `next_actions`. Responses have schemas in the installed catalog; result metrics and decisions use the shared v2 contracts. Use command JSON fields, not human log parsing.

| Exit code | Meaning |
|---|---|
| 0 | Operation succeeded; physical failure can still be present in a completed evaluation |
| 1 | Internal/local IO error |
| 2 | Invalid input or schema/usage error |
| 3 | Service unavailable or HTTP timeout |
| 4 | Ownership, revision, state or idempotency conflict |
| 5 | Record/artifact not found |
| 6 | Wait returned a cancelled/interrupted job |
| 7 | Wait timed out; the job may still be running |

Every mutation has an operation ID. CLI commands require `--operation-id` except opening/revision, which include it in the request JSON. The CLI reads the current revision and owner by default; `--revision` and `--actor` allow explicit optimistic concurrency. Reusing a key with the same payload returns the same operation/job, even after completion or cancellation. Changed content under an old key is a 409/exit 4. Do not generate a new key merely because an HTTP connection was lost: inspect the original operation/job first.

Verification, reference building and evaluation return HTTP **202** with a durable queued job, not a blocking simulation response. Poll `external job ID JOB_ID` or `external wait`. A single job may run all tests in the frozen suite. The existing workspace worker processes explicitly queued physical work and never sends an external experiment into the managed reasoning loop. Jobs wait while that loop owns the workspace execution slot.

`external cancel ID --operation-id stop-1` cancels queued work immediately or signals the active sandbox. `external resume ID --operation-id resume-1` restores a safe phase; it does not requeue a cancelled/interrupted operation. Inspect evidence and submit a new operation ID when an explicit retry is appropriate. Queued jobs survive server restart. Running jobs are interrupted/fenced on restart and require explicit resume. Historical job IDs remain queryable after newer work begins. No model call or embedding lookup is part of recovery.

The actor label is not authentication. This is a single-user localhost service with existing host/origin protection, not a remote multi-user deployment.

## HTTP operation mapping

Use `/api/v2/experiments` for POST opening and GET listing. Other paths below are relative to `/api/v2/experiments/{id}`; mutations include `actor`, `revision`, `operation_id` unless noted.

| HTTP operation | CLI |
|---|---|
| GET experiment | `external status` |
| POST `/plan` (full draft requirements/tests/evaluator/runtime) | `external plan` |
| GET `/plan-validation`, `/capabilities` | `external validate-plan`, `external capabilities` |
| POST `/fixtures` (STEP base64) | `external fixture` |
| POST `/reference-builds`, `/verify`, `/evaluate` → 202 | `external reference-build`, `external verify`, `external evaluate` |
| GET `/jobs/{job_id}`, `/results` | `external job` / `wait`, `external results` |
| POST `/freeze`, `/candidates`, `/reflections`, `/finalize` | `external freeze`, `submit`, `reflect`, `finalize` |
| POST `/cancel`, `/resume` | `external cancel`, `resume` |
| POST `/revisions` (new OpenExperiment) | `external revise` |
| GET `/report` | `external report` |

Retrieval uses GET `/api/v2/experience?q=...`; artifact bytes use GET `/api/v1/artifacts/{artifact_id}`. The runtime resolver is GET `/api/v2/runtimes/resolve?image=...` and inspects only an installed Docker image. It does not install dependencies, fetch models, or run a simulation. There is no client endpoint for trusted scores or acceptance.

## Compatibility

The v1 YAML/UI/custom-task route is retained. Prior v2 synchronous Python service methods remain available to in-process adapters, but external clients should use the service APIs. The v2 HTTP `/verify` and `/evaluate` responses now return queued job records (202) instead of completed run records; clients written for Prompt 1 must poll and then fetch results/status. Existing records are not rewritten. The conservative harness implementation identity changes, so previously frozen v2 suites need linked revision/reverification before new evidence can be produced by the changed implementation. Historical records and reports remain readable.
