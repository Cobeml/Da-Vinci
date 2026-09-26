# Da Vinci: Recursive Improvement CAD Harness

A CAD harness for the MongoDB Atlas Hackathon. GPT-6 Astra generates physical components, reviews independent evaluations, creates reusable tools and carries lessons into subsequent designs. Model weights stay fixed.

The main demo is a **three-part parallel-jaw gripper**. The agent chooses rib connectivity, node locations and section sizes for the moving fingers. An independent evaluator checks four structural load cases and actual CAD clearance at nine jaw openings. The Next.js page shows every attempt with interactive opening controls, a frame-stress view and quantitative comparisons.

**Stack:** Next.js / React · Python · CadQuery · GPT-6 Astra · MongoDB Atlas

[Open the demo on the configured Tailscale network](http://100.99.98.39:8086) · [Gripper plan and evaluation guide](docs/studies/gripper.md) · [Earlier sensor-mount study](docs/sensor-gallery.md)

## Self-improvement methods

1. **Reflect and remember.** A review-agent call interprets measured stress, displacement, buckling and clearance after each attempt. Atlas Vector Search retrieves relevant prior outcomes; saved lessons become the next working policy.
2. **Create and reuse tools.** Astra writes a member-sizing utility after the first two designs. It passes six independent checks, then runs before subsequent proposals.
3. **Evaluate and revise.** Change rib topology and dimensions, evaluate the actual CAD and keep the lightest passing jaw pair. Every attempt remains visible, including heavier alternatives and failed checks.

## MongoDB Atlas

- **Documents** store designs, evaluations, tools and policies.
- **Vector Search** retrieves prior results within the matching specification and evaluator cohort.
- **GridFS** preserves CAD files and source snapshots.
- **Database Triggers** enqueue evaluation and reflection in the full two-specialist workbench. The gripper study uses a sequential Python loop with the same Atlas archive and memory services.

## Improvement by model

<!-- gripper-results:start -->

**523.6 → 193.2 g: 63.1% less moving jaw mass.** Total three-part mass falls from 887.5 to 557.1 g. The guide base is unchanged.

| Iteration / STEP | Rib layout | Moving mass (g) | Total mass (g) | Tip displacement est. (mm) | Stress est. (MPa) | Result |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| [01](web/public/models/gripper/01-model.step) | Conservative baseline frame | 523.6 | 887.5 | 0.002 | 1.9 | Baseline |
| [02](web/public/models/gripper/02-model.step) | Tapered triangular frame | 207.1 | 570.9 | 0.047 | 15.9 | Passed |
| [03](web/public/models/gripper/03-model.step) | Slim two-leg triangle | 198.5 | 562.3 | 0.062 | 20.3 | Passed |
| [04](web/public/models/gripper/04-model.step) | High-junction Y frame | 193.5 | 557.4 | 0.120 | 54.4 | Passed |
| [05](web/public/models/gripper/05-model.step) | Minimum-section direct legs | 194.6 | 558.4 | 0.071 | 22.1 | Passed |
| [06](web/public/models/gripper/06-model.step) | Canted minimum-width Y | 193.4 | 557.3 | 0.143 | 74.8 | Passed |
| [07](web/public/models/gripper/07-model.step) | Stepped knee-braced mast | 193.2 | 557.1 | 0.246 | 77.1 | Best passing |
| [08](web/public/models/gripper/08-model.step) | Inclined Shared Spine | 193.3 | 557.1 | 0.246 | 79.7 | Passed |

The study changes topology as well as section sizes: a heavily braced baseline becomes a tied triangle, direct legs and Y-shaped alternatives. Lighter designs can have higher stress or displacement. All attempts and their review notes remain visible; the best label uses unrounded measurements.

All eight attempts passed the fixed screen. Recorded API accounting was $4.39 within the $25 cap, including a conservative reservation charged for one timed-out request.

Values come from the [exported study records](web/data/gripper-gallery.json). Research context and measurement scope are expandable below.

<!-- gripper-results:end -->

<details>
<summary><strong>Research evidence</strong></summary>

**Reflection and memory.** [Closing the Consistency Gap — 8 September 2026](https://arxiv.org/abs/2609.08832) reported **+16 percentage points** in AppWorld tasks succeeding on all five runs, using stored diagnostic guidelines with ReAct/GPT-4.1; **+13 points** on similar tasks.

**Reusable skills.** [SkillAlchemy — 24 August 2026](https://arxiv.org/abs/2608.23417) reported **+19.9 percentage points** pass rate over execution without skills across 87 SkillsBench tasks, by creating reusable skill packages from source material.

**Evaluation and revision.** [AIDE² — 22 September 2026](https://arxiv.org/abs/2609.26457) found **7 successive agent improvements in 8 days** by testing changes to its own code. Gains transferred to four held-out benchmarks.

These are recent preprints. Their results come from other tasks; they do not validate this CAD harness or measure each method's contribution to its mass reduction.

</details>

<details>
<summary><strong>Agent harness setup</strong></summary>

### Graph design and independent evaluation

Astra uses high reasoning to choose a graph of rectangular ribs within fixed carriage and gripping-pad interfaces. CadQuery builds the guide base and two mirrored jaws in a container without network access or credentials. A separate trusted container verifies the exported STEP against the graph and fixed interfaces; it never imports candidate code.

A linear 3D beam-frame solver checks pinch, payload, lateral and combined loads. Fixed limits are 80 MPa nominal normal stress, 0.25 mm tip displacement and a pinned-member buckling factor of 2. BRep checks test collisions at nine openings between 20 and 60 mm, with 0.25 mm minimum running clearance and sample gauges at both endpoints.

After each evaluation, a separate review call records lessons and the next design focus. The validated sizing tool, actual tool executions, prior measurements and retrieved Atlas memories enter later prompts. Git versions source and context; Atlas and GridFS retain the evidence. The study resumes under a $25 total API cap with cached responses. The gallery reads a static export without making model or database calls.

### Full multi-agent workbench

The workbench at `/harness` coordinates structural and aerodynamic specialists against a shared vehicle specification. Two Python workers process durable jobs. Atlas triggers enqueue evaluation and reflection; a recovery loop repairs missed delivery. A meta-agent proposes tested tools and versions of `orchestrator.py`, `policy.json` and an isolated React `PolicyNote.tsx` panel. Independent tests and CAD checks gate activation. The evaluator, acceptance limits, permissions and API budget remain outside the editable release.

The gripper study uses a sequential loop rather than that two-specialist queue. Its richer graph family has a separate evaluator and scoring cohort.

### Measurement scope

The objective is moving jaw-pair mass. Total assembly mass also includes the unchanged guide base; both are measured from STEP volume using nominal aluminium density. Frame results assume rigid beam joints and fixed carriage roots, with loads applied at the defined tip node; pad compliance and offset force couples are not modeled. They do not model local joint, bearing, contact, shear, torsional stress or fatigue behavior. An external actuator and friction pads are required; those are outside this passive mechanism study. The opening slider is continuous, while collision validation samples nine positions.

See [the build plan and reproducibility commands](docs/studies/gripper.md), [system architecture](docs/architecture.md) and [earlier verification results](docs/verification.md). The original sensor study remains at `/sensor`, with its 83.5 → 30.3 g result and archived assets intact.

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

To resume the gripper study or republish its archived results:

```bash
# Live generation: resumes the same study and its existing budget cap.
.venv/bin/python -m scripts.gripper_study --count 8

# Export completed records without new model calls.
.venv/bin/python -m scripts.gripper_study --export-only
npm run build
# Stop the existing development stack before starting production.
bash scripts/dev.sh --production
```

Relevant checks:

```bash
.venv/bin/python -m pytest -q -m 'not integration'
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_gripper.py
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_integration.py
npm run typecheck
npm run build
# With the application running:
node_modules/.bin/playwright test tests/browser/gripper-gallery.spec.ts
```

See the [laptop-access guide](docs/demo/README.md) for private Tailscale access and startup after reboot. The earlier Quarto report remains available separately; the Next.js gallery is the main presentation.

</details>
