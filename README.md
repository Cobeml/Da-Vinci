# Da Vinci

A multi-agent CAD workbench for the MongoDB Atlas Hackathon. Two specialists generate components of one vehicle; an independent evaluator measures their exported geometry; a meta-agent creates tools and proposes tested changes to the harness.

**Implemented:** Next.js/React 3D workbench, Python workers, real CadQuery STEP/GLB generation, structural/aerodynamic screening, shared-assembly checks, durable jobs, failure memory, generated Python tools, automatically tested releases, Git archives, browser inspection, and portable run exports.

**Two explicit modes:** `replay` uses deterministic specialist/meta-agent fixtures and makes no model calls. `live` uses GPT-6 Astra through the Responses API. Both run actual CAD and evaluations. Local storage uses SQLite; configuring `MONGODB_URI` switches the repository to Atlas, GridFS, and vector retrieval. Astra-driven CAD, Atlas persistence, GridFS, and vector retrieval have passed live checks. Atlas Database Triggers also passed independent delivery checks. See [verification](docs/verification.md) for results and limitations.

## Start locally

The main page is an [interactive sensor-mount gallery](http://100.99.98.39:8086), with every Astra iteration, measured characteristics and a per-model VTOL view. See the [sensor gallery guide](docs/sensor-gallery.md) for its bounded generation workflow. The full workbench is at `/harness`. The earlier [Quarto report](http://100.99.98.39:8085) and [laptop-access guide](docs/demo/README.md) remain available.

Requirements: Linux, Docker, Node 22+, and [uv](https://docs.astral.sh/uv/). Run from this directory:

```bash
uv sync --frozen
npm ci
npm ci --prefix sandbox/ui
docker compose --profile build build cad-image
.venv/bin/python -m playwright install chromium
bash scripts/dev.sh
```

Open **http://127.0.0.1:3215** for the gallery or **http://127.0.0.1:3215/harness** for run controls. The Python API listens on **127.0.0.1:8215**; its OpenAPI explorer is at `/docs`. The dedicated ports avoid the existing applications on this workstation. Stop the development stack with Ctrl+C.

Click **Start replay run**. A fresh ledger demonstrates deliberately thin/poor-clearance candidates, independent failures, generated tool validation, a policy/orchestration/UI release, and improved geometry. Later runs start from the learned release and reuse the saved tool. To replay from an entirely fresh state without deleting history, use another data directory:

```bash
DAVINCI_DATA_DIR=runtime/fresh .venv/bin/python -m scripts.demo --rounds 4
```

The CLI runs the same durable job handlers without needing the browser. Do not run multiple stacks against the same ledger; the supported worker process already runs two workers.

## Connect Atlas and Astra

Copy `.env.example` to `.env`, then set `OPENAI_API_KEY` and `MONGODB_URI` **server-side**. Keep the file untracked. Follow [Atlas setup](atlas/README.md) to create indexes and the two Database Triggers:

```bash
.venv/bin/python -m scripts.check_connections --public-ip
.venv/bin/python -m scripts.atlas_setup
```

Set `DAVINCI_USE_ATLAS_TRIGGERS=true`, restart the stack, then choose **Astra live** in the workbench. There is no silent fallback from a live model request to a replay fixture. The UI reports missing credentials or runtime failures.

The Atlas trigger functions only upsert durable jobs. Local Python workers execute CAD, inference, and reflection. A 15-second reconciliation pass repairs missed trigger delivery. Vector retrieval filters by project, subsystem, specification, and evaluator version; recent results are also injected directly because indexing is asynchronous. Failed embedding calls can be retried with `.venv/bin/python -m scripts.backfill_memory` within the original run's budget.

For the resumable, budgeted setup and validation sequence, see [live validation](docs/live-validation.md).

## What the demo evaluates

- **Structural:** a uniform sensor-mount plate with two fixed mounting holes. Optimization varies thickness; mass is measured from STEP volume. Nominal beam stress and deflection are screening calculations. Arbitrary cutouts, changed datums, and unsupported geometry fail the reference-family check.
- **Aerodynamic:** a symmetric NACA0012 extrusion split into fixed and moving surfaces. Span, flap fraction, and hinge gap vary. The evaluator checks the reference family, clearance through sampled travel, required lift coefficient, and an induced-drag estimate at fixed lift.
- **Assembly:** both evaluated STEP files are transformed into the shared frame, checked for collisions including flap travel, checked against their joint mass budget, and exported together.
- **Ranking:** feasibility first; then the equal-weight normalized assembly mass and induced-drag objective. All feasible assembly snapshots are retained; the champions endpoint also computes their Pareto frontier.

These are low-order screening results. The demo does not perform FEA, viscous CFD, hover/rotor interactions, or flight validation. The generated projected-area tool explicitly reports a bounding-box proxy, not drag. Higher-fidelity solvers are the next engineering phase.

## Self-improvement boundary

Generated CAD runs without network access or credentials in a disposable container. A fresh container evaluates the resulting STEP file and never imports candidate code. The runner pins the image ID, limits execution to 2 CPUs/4 GiB, and allows at most two simultaneous containers per worker process.

The meta-agent edits three real files in versioned release snapshots:

| Editable file | How it becomes active |
|---|---|
| `orchestrator.py` | Its `adapt(parameters, policy, subsystem)` function executes in a sandbox before subsequent CAD generation |
| `policy.json` | Versioned heuristics and lessons enter future agent context |
| `PolicyNote.tsx` | Compiled and rendered in a sandbox, then displayed as an isolated React-authored workbench panel |

The release gate runs independent adaptation fixtures, React compilation/rendering, and real CAD canaries. A passing revision activates at the round boundary; an orchestration execution failure restores the previous active pointer. The trusted evaluator, acceptance specification, API budget, permissions, and promotion service stay outside the writable release snapshot. UI self-editing currently targets the policy panel; it does not redeploy the whole Next.js application.

Tools have immutable Git commits, schemas, validation evidence, and artifact bundles. The initial dynamic-tool contract is `directional_projected_area`; additional domain tools require an independent validation contract before activation. The model generates the Python implementation in live mode.

## Persistence and reproducibility

- `runtime/ledger.sqlite3`: durable local document ledger, including jobs and checkpoints.
- `runtime/repository`: permanent Git history for candidate code, tools, releases, and environment snapshots.
- `runtime/artifacts`: content-addressed artifacts; Atlas mode additionally stores them in GridFS.
- **Archive → Export run bundle:** JSON ledger records, referenced releases/tools/policies, STEP/GLB geometry, logs, screenshots, hashes, and the run's pinned environment source/lockfiles.

Changing the demo specification creates a new content-derived specification ID. Changing the evaluator source creates a new scoring cohort; scores are not compared across cohorts. Artifacts and evidence are append-only through application interfaces. This is not a database-level immutability guarantee.

API keys never enter generated-code containers. If configuring an API token, set `DAVINCI_API_TOKEN`; the Next.js server proxy forwards it without exposing it to the browser. The default deployment binds only to loopback. Public hosting, multi-user authentication, and distributed runners require a separate deployment configuration.

## Checks

```bash
.venv/bin/python -m pytest -q -m 'not integration'
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_integration.py
npm run typecheck
npm run build
# With a running stack and at least one completed replay:
npm run test:e2e
# Optional resource measurements: ten candidates each at one/two workers
.venv/bin/python -m scripts.benchmark
```

Browser tests cover real model rendering, camera controls, mobile containment, memory/tools/archive navigation, ZIP export, and run cancellation. Integration tests build actual CAD in Docker, validate engineering failures, exercise generated-tool reuse after restart, and test release rejection.

In a restricted execution environment, Docker access, localhost listeners, browser installation, and API-test event loops may require running these commands outside that sandbox. The generated code still runs inside the harness's isolated containers.

## Configuration defaults

Ten design rounds maximum; four in the UI; stop after three rounds without improvement. API spending is reserved before requests: $10/run and $50/day by default. Unknown-cost failed requests are charged their conservative reservation; reservations left by a crash remain held. These application limits supplement provider-side billing limits. Two workers, 120-second CAD build timeout, 60-second evaluation/tool timeout, and three infrastructure attempts.

No automatic deletion of historical evidence is enabled. Monitor disk/Atlas storage during sustained use. Large-scale artifact retention and physical solver calibration remain follow-up work.

See [architecture and data flow](docs/architecture.md) for the implementation map and [Atlas configuration](atlas/README.md) for deployment steps.
