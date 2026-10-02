# Simulation adapters and evidence

Da Vinci runs scoped engineering checks through the existing lifecycle and sandbox runner. The external agent and managed driver use the same validation, evaluation, and acceptance operations. No model provider or embedding service is involved in simulation operations. SQLite/local artifacts remain the default; Atlas/GridFS remain optional. This phase adds no database migration or scheduler.

## Discovery and supported physics

`davinci external adapters` works offline, including from an installed wheel without CadQuery or NumPy on the host. GET `/api/v2/simulation-adapters` returns the same versioned descriptors. `external schemas` and GET `/api/v2/schemas` include `SimulationSpec`, `AdapterDescriptor`, `ArtifactManifest`, and the extended plan/runtime/result schemas.

| Adapter | Scope and fidelity | Available route | Main limitations |
| --- | --- | --- | --- |
| `sensor-screen` | STEP mass and conservative uniform wall-strip stress/deflection | Existing sensor task | Fixed cradle family; nominal PA12; no joints, anisotropy, vibration or FEA |
| `gripper-screen` | Linear frame stress/deflection, pinned-member buckling, nine BRep travel positions | Existing gripper task | Fixed jaw graph; rigid joints; no continuous collision, contact or dynamics |
| `vtol-screen` | Component mass, VLM with archived XFOIL polars, mission energy and beam screening | Existing VTOL task | Fixed family/maps; no rotor interference, transition dynamics, flutter, fatigue or flight validation |
| `authored-screen` | Independently verified task-authored analytic screening | V2 custom task and legacy custom compatibility | Mass, linear static and geometry only; linear isotropic material. Not a generic structural solver |
| `calculix-static` | Optional Gmsh/CalculiX converged C3D10 static solids | V2 external and managed operations | One connected isotropic solid; planar clamps/uniform face load; small deformation; predeclared gauge-mean stress; no nonlinear/contact/fatigue qualification |

See [optional structural simulation](structural-simulation.md) for installation, exact scope, units, convergence, independently specified references and the varied-feature bracket walkthrough. `davinci setup --template structural` builds its optional runtime; discovery does not install it.

The descriptors state geometry/material assumptions, required software, fidelity limits, and reference checks. Setup validation and resource estimation use `adapters.assess`; preparation and execution use `execution.build/evaluate_test`; extraction uses `execution.score`; lifecycle `verify` checks independent positive and negative references. Legacy task preparation/extraction stays in `tasks.evaluate/score_evaluation`, with adapter discovery and runtime checks shared. Legacy formulas and acceptance numbers are unchanged. Declaring a fixed-family legacy adapter in a V2 custom bundle returns an unsupported capability: this release does not translate the legacy family contract into a V2 task.

Optional solver libraries live in the pinned Docker runtime, not mandatory host dependencies. `davinci setup --template custom` builds the CAD/NumPy runtime. `--template vtol` builds the AeroSandbox runtime. No solver or cloud image is installed automatically by capability checks. Package versions are discovered by importing them inside the pinned sandbox and retained in capability evidence; declared versions require exact matches. The image digest also pins native libraries and solver binaries. A successful import is not a physical reference check.

## Author a simulation test before generating candidates

Add `simulation` to each new test. The installed external beam example includes this declaration and a structured root interface:

```json
{
  "version": 1,
  "adapter": "authored-screen",
  "phenomena": ["mass", "linear_static"],
  "material_model": "linear_isotropic",
  "geometry_assumptions": "Single rectangular 40 by 20 mm cantilever",
  "fidelity": "analytic_screen",
  "stage": "final",
  "cad_unit": "mm",
  "solver_length_unit": "mm",
  "required_software": {"cadquery": null, "numpy": null},
  "estimate": {
    "cpu_cores": 1, "memory_mb": 512, "disk_mb": 128, "wall_seconds": 30,
    "basis": "Small analytic beam and OCP geometry operations",
    "uncertainty": "Peak memory unknown; pilot execution required"
  },
  "required_evidence": []
}
```

`required_evidence` may include `mesh`, `solver_deck`, `fields`, `convergence`, and `uncertainty`. The evaluator must export the requested evidence: `.msh`, `.inp`/`.dat`, `.vtk`/`.vtu`/`.npz`/`.csv`, `convergence.json`, and `uncertainty.json`, respectively. Empty/missing required outputs cannot pass. These are evidence artifacts, not additional trusted score channels. Per-metric numerical error and uncertainty still must satisfy the frozen `accuracy` contract. A convergence JSON file alone does not establish adequate physics or numerical accuracy; verify the evaluator and reference values independently.

Preserve all fixed loads, physical interfaces, material provenance, applicability limits and acceptance thresholds in the plan. Editable parameters stay in `design_schema`. The acceptance-suite identity includes these declarations and harness implementation sources, but excludes the candidate builder.

A `preliminary` test may accompany required final tests. Every required test runs on every requested evaluation, at its declared fidelity. Final acceptance requires required final-stage coverage of every critical requirement, all required tests passing, complete retained evidence, and a non-draft suite. A preliminary result cannot stand in for the final test, even if its metrics pass. This release does not cache a preliminary result as final evidence or choose a cheaper solver. Finalization rechecks the recorded final suite and artifact checksums; it does not automatically schedule another paid call or rerun the solver. Objective targets and search stopping conditions remain separate from acceptance.

## Units and semantic regions

New simulation declarations validate dimensions using an explicit supported-unit vocabulary (`units.py`). Examples include mm/m, MPa/Pa, g/kg, g/mm3/kg/m3, N, m/s, seconds/minutes, W and Wh. Unknown units or mismatched dimensions are invalid setup. The original exact-unit comparison remains available for compatibility plans without `simulation`.

CadQuery/OCP imports and the builder contract use millimetres. Independent preparation computes and records the CAD-to-solver length scale, exports a separate scaled `solver.step`, and passes its location and units in `request.geometry`. `model.step` stays in CAD units. Evaluators must explicitly use the appropriate file and convert loads/materials consistently; the service does not silently reinterpret the evaluator's variables. Returned measurements, numerical errors and uncertainty bounds are converted together into compatible declared metric units before threshold comparisons.

Each physical interface in a new plan needs a `region` rule, for example:

```json
{
  "kind": "planar_face",
  "center": [-20, 0, 0], "normal": [-1, 0, 0],
  "center_tolerance": [0.00001, 0.00001, 0.00001],
  "normal_tolerance_degrees": 1,
  "extent_min": [0, 20, 1], "extent_max": [0.00001, 20, 10],
  "expected_count": 1
}
```

Coordinates/extents use the interface's declared length unit. After STEP reimport, a separate trusted CadQuery inspection exports face centers, outward normals, extents and areas. The host matches location, orientation, extent and exact expected count. It does not consume face indices, CAD labels or candidate-provided hints. Missing or ambiguous matches are `invalid_setup/invalid_binding`; the evaluator is not run. The independently determined bindings replace evaluator-provided booleans. Current structured selectors support planar faces only; curved surfaces and volumetric region selection require a future adapter, not a guessed face label.

## Capabilities and budgets

`external capabilities ID` / GET `/api/v2/experiments/ID/capabilities` combines reference verification with the particular test's physics, material, units, software and resource requirements. Reports include affected requirement IDs, blockers, what capability is needed, and available approximation fidelities. They explicitly report that no substitution was performed. The managed author receives the same adapter catalog.

Local probes consider CPU affinity, cgroup CPU/RAM limits, available RAM, Docker daemon CPU/RAM and free artifact disk space. Packages are checked in the actual pinned runtime. CPU-only adapters do not require or infer a GPU. GPU requests and remote backends report unavailable/unsupported: no accelerator executor or remote executor is shipped, and no resources are provisioned automatically. Docker contexts must be local Unix sockets.

Runtime fields bound per-job `cpu_cores`, `memory_gb`, `timeout_seconds`, total `job_seconds`, conservative allocated-CPU `compute_seconds`, `artifact_bytes`, `file_bytes` and `log_bytes`. Cumulative candidate-build and test time/output budgets apply across a candidate evaluation. Docker retains network isolation, read-only root, dropped capabilities, unprivileged UID, process limit and bounded tmpfs. CPU/memory/file-size limits are kernel-enforced; aggregate output/log limits are polled and checked again before collection. Aggregate disk writes can briefly overshoot between polls; this is not a reserved filesystem quota. Collected artifacts remain bounded. The current runner supports flat output files only.

Resource estimates are uncertain admission estimates, not adequacy proofs. Actual wall time, allocated CPU upper bounds, output sizes, configured limits and omissions are retained in `resources.json` and `timing.json`. Pilot observations refine timing/output estimates; the shared runner does not measure peak memory. The optional structural adapter additionally retains per-process/solver RSS maxima and post-mesh estimates, with their measurement limits. No mesh quality, convergence, or uncertainty is inferred from machine capacity. Geometry-specific validity, numerical accuracy and references still determine whether evidence is usable.

Cancellation stops the running container; queued cancellation/restart ownership rules are unchanged. Timeout, cancellation, resource exhaustion, artifact quota, missing solver, unsupported physics/material, invalid units/bindings, numerical error and physical failure remain distinct. Failed jobs preserve available bounded output and logs before temporary directories are removed.

## Artifacts, provenance and report checks

Evaluation results include the existing STEP/GLB artifact references plus a versioned manifest. Entries identify role, content type, byte size, SHA-256 and artifact ID for CAD, meshes, bindings, solver decks, logs, resource timing, fields, convergence/uncertainty and raw results. Manifest provenance links candidate source/version, plan, evaluator, runtime, suite and harness execution identities. Verification/reference records retain their own evidence. Legacy evaluations also retain logs, raw result JSON and timing; archived documents are untouched.

Simulator output filenames must be flat and have allowed suffixes; scripts/HTML, symlinks, directories and oversized outputs are not accepted as evidence. JSON must parse; GLB needs its magic header. STEP validity is determined by independent CAD import, not its extension. Rejected outputs are recorded as omissions and make the manifest incomplete. Host-generated resource/binding records cannot be replaced by evaluator outputs.

`Artifacts.put_stream` supports bounded chunked local/GridFS ingestion. `verified_open` checks size and SHA-256 before returning a seekable stream, spooling larger payloads to disk. The artifact HTTP endpoint streams from this verified snapshot with `nosniff` and download disposition. It does not render solver HTML in the trusted localhost origin. The runner currently gathers a bounded output bundle in memory before archival; it is not an unbounded multi-gigabyte field pipeline. Finalization verifies every referenced artifact and recomputes the manifest and acceptance decision.

## Compatibility and reproduction

No stored records are rewritten. V1 custom/builtin tasks keep their legacy semantics and `legacy-unverified-coverage` label; retaining more evidence does not retrospectively grant test-first or final-suite guarantees. Earlier V2 plans without `simulation` remain loadable through the exact-unit/evaluator-owned binding compatibility path. They are not upgraded to independent structured-region checks. Old frozen execution identities are read-only under a changed harness: open a linked revision, add the simulation declaration/region rules, reverify, then reevaluate. Unfinished old runs must not silently change their frozen evaluator.

From a checkout with dependencies and local Docker images already installed:

```bash
uv run pytest -m 'not integration' -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py tests/product/test_external_cli.py tests/product/test_simulation.py -m integration -q
uv run davinci external adapters
uv run davinci external schemas
```

For the public keyless route from a fresh workspace:

```bash
davinci init /tmp/davinci-simulation --template custom --driver external
davinci setup --template custom
cd /tmp/davinci-simulation
davinci service ensure
python external/walkthrough.py
```

The walkthrough creates positive/negative reference fixtures, freezes the scoped beam screen, measures a failed thin beam and passing revision, downloads artifacts and exports a report. It uses only supported HTTP operations through the workspace service. It does not need model keys, embeddings, host CAD libraries, or Atlas. See [external agents](external-agents.md) for individual CLI operations, job polling, cancellation/resume and linked corrections.


## Product setup and preview

`davinci setup --template sensor` builds `da-vinci-cad:local`; `--template vtol` also builds `da-vinci-vtol:local`. The managed request form resolves an installed image to its digest, and the capabilities view reports unavailable software/physics/resources. No cloud resources are provisioned. A GPU does not establish adequacy.

V2 evaluation now derives an optional GLB preview from exported STEP in a separate trusted container, under the existing job time/resource/artifact bounds. Candidate glTF files cannot replace it. Preview logs and errors are retained separately from builder/solver evidence. Updated execution identities require linked revisions for old frozen suites; archives are not rewritten.

CI runs `uv run python scripts/required_native.py`. It checks the required image tags before executing integration tests, and fails if core physics/parity tests are absent or skipped. Fast tests remain a separate job. The only allowed intentionally skipped native selection is the separately opt-in paid model smoke.
