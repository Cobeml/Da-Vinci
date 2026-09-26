# Da Vinci: Recursive Improvement CAD Harness

A CAD harness for the MongoDB Atlas Hackathon. GPT-6 Astra generates drone sensor mounts. The harness evaluates each attempt and carries reusable tools and lessons into subsequent designs.

The Next.js page shows eight interactive models, their measured characteristics and the best passing design. Each model can be viewed alone or mounted on an illustrative VTOL.

**Stack:** Next.js / React · Python · CadQuery · GPT-6 Astra · MongoDB Atlas

[Open the demo on the configured Tailscale network](http://100.99.98.39:8086) · [Sensor study guide](docs/sensor-gallery.md)

## Self-improvement methods

The agent improves its tools and working context between CAD attempts. Model weights stay fixed.

1. **Reflect and remember.** Retrieve prior designs and measurements; carry lessons into the next attempt.
2. **Create and reuse tools.** Write, test and save a wall-thickness utility for subsequent designs. After two attempts, Astra created the utility; five validation cases passed before it was reused from iteration 3 onward.
3. **Evaluate and revise.** Use independent CAD checks to guide revisions; retain the lightest passing design.

## MongoDB Atlas

- **Documents** store designs, evaluations, tools and policies.
- **Vector Search** retrieves prior results for the next attempt, scoped to the relevant specification and evaluator.
- **GridFS** stores CAD files and source snapshots.
- **Database Triggers** enqueue evaluation and reflection jobs in the full multi-agent workbench. The sensor study below uses a sequential Python loop with Atlas storage and memory.

## Improvement by model

**83.5 → 30.3 g: 63.7% mass reduction.** All eight designs passed the same screening checks: nominal PA12, a 20 N load, deflection ≤ 0.65 mm and stress ≤ 28 MPa. The mounting footprint remains 100 × 72 mm with an 80 × 52 mm bolt pattern.

| Iteration / STEP | Design | Mass (g) | Reduction vs. baseline | Deflection est. (mm) | Stress est. (MPa) | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| [01](web/public/models/sensor/01.step) | Solid cradle | 83.535 | — | 0.053 | 0.66 | Baseline |
| [02](web/public/models/sensor/02.step) | Open-window cradle | 30.362 | 63.7% | 0.647 | 4.51 | Improved |
| [03](web/public/models/sensor/03.step) | Open-window refinement | 30.333 | 63.7% | 0.650 | 4.52 | Improved |
| [04](web/public/models/sensor/04.step) | Open-window refinement | 30.332 | 63.7% | 0.650 | 4.52 | Passed |
| [05](web/public/models/sensor/05.step) | Open-window refinement | 30.332 | 63.7% | 0.650 | 4.52 | Passed |
| **[06](web/public/models/sensor/06.step)** | **Open-window refinement** | **30.332** | **63.7%** | **0.650** | **4.52** | **Best passing** |
| [07](web/public/models/sensor/07.step) | Ribbed cradle, three slots | 31.666 | 62.1% | 0.650 | 4.49 | Passed |
| [08](web/public/models/sensor/08.step) | Ribbed cradle, two slots | 31.211 | 62.6% | 0.650 | 4.49 | Passed |

The largest reduction came from replacing the solid baseline with thinner walls, oval windows and a base slot. Iterations 3–6 reused the saved thickness tool for small refinements; the final differences are below the table's displayed precision. Iterations 7–8 tested diagonal ribs and gussets but remained heavier than iteration 6.

Values come from the [exported study records](web/data/sensor-gallery.json). Ranking uses unrounded measurements. Every attempt remains in the gallery, including alternatives that did not improve the best result.

<details>
<summary><strong>Research evidence</strong></summary>

**Reflection and memory.** [Closing the Consistency Gap — 8 September 2026](https://arxiv.org/abs/2609.08832) reported **+16 percentage points** in AppWorld tasks succeeding on all five runs, using stored diagnostic guidelines with ReAct/GPT-4.1; **+13 points** on similar tasks.

**Reusable skills.** [SkillAlchemy — 24 August 2026](https://arxiv.org/abs/2608.23417) reported **+19.9 percentage points** pass rate over execution without skills across 87 SkillsBench tasks, by creating reusable skill packages from source material.

**Evaluation and revision.** [AIDE² — 22 September 2026](https://arxiv.org/abs/2609.26457) found **7 successive agent improvements in 8 days** by testing changes to its own code. Gains transferred to four held-out benchmarks.

These are recent preprints. Their results come from other tasks; they do not validate this CAD harness or measure each method's contribution to its mass reduction.

</details>

<details>
<summary><strong>Agent harness setup</strong></summary>

### This sensor-mount study

1. **Set the design contract.** A Python runner fixes the mounting footprint, material assumptions, load and acceptance limits. Astra writes CadQuery wrappers and chooses dimensions within the supplied cradle family.
2. **Build and measure.** Candidate code runs without credentials or network access in an isolated Docker container and exports STEP and GLB. A separate evaluator checks the exported STEP against the supported geometry family, measures volume and applies the same stress and deflection screen to every attempt. It never imports candidate code.
3. **Reflect and reuse.** Previous results, scoped Atlas Vector Search matches and accumulated lessons enter the next prompt. The generated wall-thickness utility passes four numeric cases and an invalid-input case before activation; subsequent attempts receive actual executions of that saved tool.
4. **Archive and select.** Git versions source, tools and context. Atlas stores records and GridFS stores artifacts. The runner retains the lightest passing design. The gallery reads an exported snapshot, so browsing it makes no model calls or database requests.

The eight-attempt study resumes under one $3 total API budget cap. Recorded API usage was approximately $0.77. The first six attempts refined the open-window design; two additional comparisons tested ribbed alternatives. Records are stored in `design_iterations` and `design_tools`, with scoped memories in `memories`.

### Full multi-agent workbench

The workbench at `/harness` coordinates **structural** and **aerodynamic** specialists against a shared vehicle specification. Two Python workers process durable jobs. Atlas candidate-insert triggers enqueue evaluation; evaluation-insert triggers enqueue reflection. A recovery loop repairs missed trigger delivery.

The structural specialist produces a sensor-mount plate; the aerodynamic specialist produces fixed and moving NACA0012 surfaces. Independent checks cover component geometry, structural screening, hinge clearance and an induced-drag estimate. Shared-assembly checks cover collisions, control-surface travel and combined mass.

A meta-agent proposes reusable tools and versioned changes to three files:

| Editable file | Role |
| --- | --- |
| `orchestrator.py` | Adapts parameters before subsequent CAD generation |
| `policy.json` | Carries heuristics and lessons into future context |
| `PolicyNote.tsx` | Renders an isolated React policy panel in the workbench |

Independent tool tests, adaptation fixtures, React compilation and CAD checks run before activation. Passing releases activate at round boundaries; orchestration execution failures restore the previous active version. The trusted evaluator, acceptance limits, permissions and API budget remain outside the editable snapshot. UI self-editing targets the policy panel, not the entire Next.js application.

The sensor study in this gallery uses a sequential Python loop with the same sandbox, archive and memory services; it does not use the full workbench's two-specialist trigger queue.

### Measurement scope and reproducibility

Mass uses STEP volume and nominal PA12 density. Stress and deflection are wall-strip estimates, not FEA. The VTOL is illustrative; measurements cover the mount only. The study demonstrates improvement within a supplied geometry family, not unrestricted topology generation or flight validation.

Candidate code, tools, releases and environment snapshots are versioned in `runtime/repository`. Artifacts are content-addressed and stored locally plus in GridFS when Atlas is configured. Changing the specification or evaluator creates a separate scoring cohort. The full workbench can export ledger records, source, CAD, logs, screenshots and hashes as a run bundle.

See [architecture and data flow](docs/architecture.md), [sensor study details](docs/sensor-gallery.md) and [verification results](docs/verification.md).

</details>

<details>
<summary><strong>Run locally and verify</strong></summary>

Requirements: Linux, Docker, Node 22+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --frozen
npm ci
npm ci --prefix sandbox/ui
docker compose --profile build build cad-image
.venv/bin/python -m playwright install chromium
bash scripts/dev.sh
```

Open **http://127.0.0.1:3215** for the gallery or **http://127.0.0.1:3215/harness** for run controls. The Python API listens on **127.0.0.1:8215**, with its OpenAPI explorer at `/docs`. Stop the stack with Ctrl+C.

**Replay** uses deterministic specialist and meta-agent fixtures with real CAD evaluation and no model calls. **Astra live** uses GPT-6 Astra. Local persistence uses SQLite; configuring `MONGODB_URI` enables Atlas, GridFS and vector retrieval.

For live use, copy `.env.example` to `.env` if a project environment file does not already exist. Set `OPENAI_API_KEY` and `MONGODB_URI` server-side and keep the file untracked. Follow [Atlas setup](atlas/README.md) to create indexes and both Database Triggers:

```bash
.venv/bin/python -m scripts.check_connections --public-ip
.venv/bin/python -m scripts.atlas_setup
```

Set `DAVINCI_USE_ATLAS_TRIGGERS=true`, restart the stack and choose **Astra live** in the workbench. See [live validation](docs/live-validation.md) for setup checks.

To resume the sensor study or republish its archived results:

```bash
# Live generation: resumes the same study and its existing budget cap.
.venv/bin/python -m scripts.sensor_study --count 8

# Export completed records without new model calls.
.venv/bin/python -m scripts.sensor_study --export-only
npm run build
# Stop the existing development stack before starting production.
bash scripts/dev.sh --production
```

Relevant checks:

```bash
.venv/bin/python -m pytest -q -m 'not integration'
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_sensor.py
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_integration.py
npm run typecheck
npm run build
# With the application running:
node_modules/.bin/playwright test tests/browser/sensor-gallery.spec.ts
```

See the [laptop-access guide](docs/demo/README.md) for private Tailscale access and startup after reboot. The earlier Quarto report remains available separately; the Next.js gallery is the main presentation.

</details>
