# Da Vinci: Recursive Improvement CAD Harness

A CAD harness for physical engineering tasks, built for the MongoDB Atlas Hackathon. GPT-6 Astra generates designs, reviews independent evaluations, creates reusable tools and carries lessons into subsequent attempts. Model weights stay fixed.

The featured study is a **complete lift-and-cruise survey VTOL**. The agent changes fuselage proportions, wing geometry, tail, structure and component layout to improve estimated range. Every design uses the same **0.5 kg mission payload, 150 Wh battery and propulsion hardware**. Speed, payload capacity and endurance are benchmarked alongside range.

**Stack:** Next.js / React · Python · CadQuery · GPT-6 Astra · MongoDB Atlas · AeroSandbox VLM · XFOIL

[Interactive VTOL gallery](http://100.99.98.39:8086/vtol) · [Study plan and physics](docs/studies/vtol.md) · [Gripper gallery](http://100.99.98.39:8086/gripper) · [Sensor gallery](http://100.99.98.39:8086/sensor)

## Self-improvement methods

1. **Reflect and remember.** A separate review call interprets computed drag, energy, trim, structure and capability limits. Atlas Vector Search retrieves previous outcomes; saved lessons guide later proposals.
2. **Create and reuse tools.** Astra wrote an energy-sensitivity utility, reused in the corrected campaign. Four numerical and four invalid-input checks gate reuse; subsequent proposals receive actual tool outputs.
3. **Evaluate and revise.** Change the aircraft geometry, evaluate its exported STEP and compare performance under a frozen mission. Keep all attempts, including failed checks and unsuccessful alternatives.

## MongoDB Atlas

- **Documents** archive designs, quantitative evaluations, generated tools and review policies.
- **Vector Search** retrieves prior outcomes within the same specification and evaluator cohort.
- **GridFS** preserves CAD files, source bundles and artifacts.
- **Database Triggers** enqueue evaluation/reflection in the full two-specialist workbench. This VTOL campaign uses a sequential Python loop with the same Atlas archive and memory services.

## Improvement by model

**68.3 → 85.1 km estimated range: 24.6% improvement.** Supported maximum speed changes from 19.0 to 19.8 m/s; 10 km mission payload capacity stays at 0.96 kg. Battery and nominal mission payload are unchanged.

The winning geometry shortens the body from 1.08 to 0.80 m, increases span from 2.10 to 2.30 m and reduces takeoff mass from 4.38 to 3.62 kg. Later alternatives trade range against endurance and payload capacity; iteration seven remains the selected design.

| Iteration / STEP | Aircraft | Range est. (km) | Max speed est. (m/s) | Payload capacity est. (kg) | Endurance est. (min) | Takeoff mass (kg) | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| [01](web/public/models/vtol/survey-vtol-range-v2/01-model.step) | BASELINE | 68.3 | 19.0 | 0.96 | 82.3 | 4.38 | Baseline |
| [02](web/public/models/vtol/survey-vtol-range-v2/02-model.step) | Lean high-aspect-ratio survey VTOL | 77.4 | 19.5 | 0.96 | 94.4 | 3.98 | Passed |
| [03](web/public/models/vtol/survey-vtol-range-v2/03-model.step) | Broad-root range VTOL | 82.4 | 19.5 | 0.96 | 110.5 | 3.94 | Passed |
| [04](web/public/models/vtol/survey-vtol-range-v2/04-model.step) | Compact low-drag survey VTOL | 84.7 | 19.8 | 0.96 | 106.8 | 3.75 | Passed |
| [05](web/public/models/vtol/survey-vtol-range-v2/05-model.step) | Compact long-span survey VTOL | 83.9 | 19.5 | 0.96 | 110.2 | 3.79 | Passed |
| [06](web/public/models/vtol/survey-vtol-range-v2/06-model.step) | Long-span balanced-tail VTOL | 84.3 | 19.5 | 0.96 | 108.5 | 3.85 | Passed |
| [07](web/public/models/vtol/survey-vtol-range-v2/07-model.step) | Compact-span lightweight survey VTOL | 85.1 | 19.8 | 0.96 | 107.3 | 3.62 | Best passing |
| [08](web/public/models/vtol/survey-vtol-range-v2/08-model.step) | Lift-sharing survey VTOL | 84.3 | 19.5 | 0.93 | 105.2 | 3.64 | Passed |
| [09](web/public/models/vtol/survey-vtol-range-v2/09-model.step) | Stiff-root survey VTOL | 84.8 | 19.5 | 0.96 | 109.1 | 3.72 | Passed |
| [10](web/public/models/vtol/survey-vtol-range-v2/10-model.step) | Slender-wing survey VTOL | 83.3 | 19.8 | 0.96 | 97.9 | 3.68 | Passed |
| [11](web/public/models/vtol/survey-vtol-range-v2/11-model.step) | Long-span VTOL with higher-Re tail | 84.9 | 19.5 | 0.96 | 111.0 | 3.75 | Passed |
| [12](web/public/models/vtol/survey-vtol-range-v2/12-model.step) | Long-chord trim-tail survey VTOL | 85.0 | 19.8 | 0.96 | 105.4 | 3.63 | Passed |

Values come from the [archived study export](web/data/vtol-gallery.json). Payload capacity is limited by both the fixed bay and mission feasibility. The [initial campaign audit](docs/studies/vtol-v1-audit.json) preserves a superseded run with a spar/airfoil mismatch. Corrected designs use contained tapered spars and variable-section bending analysis; their ranking excludes the old results. Reported API accounting includes both cohorts. The iteration table uses one consistent campaign grid; finer-grid validation is archived separately. Recorded API accounting: **$23.86** within the $30 cap, including unsuccessful model calls.

<details>
<summary><strong>Research evidence</strong></summary>

**Reflection and memory.** [Closing the Consistency Gap — 8 September 2026](https://arxiv.org/abs/2609.08832) reported **+16 percentage points** in AppWorld tasks succeeding on all five runs, using stored diagnostic guidelines with ReAct/GPT-4.1; **+13 points** on similar tasks.

**Reusable skills.** [SkillAlchemy — 24 August 2026](https://arxiv.org/abs/2608.23417) reported **+19.9 percentage points** pass rate over execution without skills across 87 SkillsBench tasks, by creating reusable skill packages from source material.

**Evaluation and revision.** [AIDE² — 22 September 2026](https://arxiv.org/abs/2609.26457) found **7 successive agent improvements in 8 days** by testing changes to its own code. Gains transferred to four held-out benchmarks.

These are recent preprints. Their results come from other tasks; they do not validate this CAD harness or measure each method's contribution to its engineering improvements.

</details>

<details>
<summary><strong>Agent harness setup and physics</strong></summary>

### Generate, evaluate, reflect

Astra chooses parameters within the fixed aircraft family. An isolated container builds CadQuery geometry; a separate trusted container checks the STEP against an independent reference before accepting a design. The agent cannot change its evaluator, battery, hardware inventory or acceptance limits.

The evaluator combines component mass/CG, AeroSandbox vortex-lattice lift/trim/induced drag, XFOIL viscous section polars, empirical body/hardware drag and measured UIUC propeller maps. Beam calculations screen wing spars, lift booms and payload support. Pitch trim uses an all-moving tail. The mission deducts 90 seconds hover and 40 seconds transition allowance, then cruise energy, with 20% reserve at landing.

After each evaluation a review call saves a lesson and next focus. A generated utility must pass independent checks before execution; retrieved Atlas memories and tool outputs enter later proposals. Source, policy, artifacts and evaluator/image fingerprints are archived. Resuming uses cached responses and retains the original budget ledger.

### Acceptance and uncertainty

A homepage champion needs at least 10% more range, at least 95% of baseline speed and payload capacity, converged finer-grid checks and a positive range gain under combined adverse assumptions. The adverse case uses 10% less available battery energy, 20% more parasite drag and 10% more empty mass. These are scenarios, not confidence intervals.

These are engineering estimates, not flight-test results. Hardware masses, efficiency, electrical limits and transition energy are assumptions. There is no complete-aircraft CFD, dynamic transition, rotor interaction, flutter, fatigue or closed-loop controller simulation. Beam checks exclude joints and local shell buckling. Range is total cruise distance, not radius; maximum speed is the highest supported passing sweep point. Propeller shapes are display/clearance surrogates. This study does not isolate each self-improvement method's causal contribution.

### Physics sources

- [UIUC experimental APC propeller data](https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html): 16×8 lift and 12×8 cruise maps, with archived raw files and hashes.
- [AeroSandbox VLM](https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/vortex_lattice_method/): lifting-surface analysis.
- [XFOIL](https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt): generated NACA 2412/0012 viscous polars.

The [full workbench](http://100.99.98.39:8086/harness) retains two specialists, durable jobs, Database Triggers and gated meta-agent tool/policy releases. The VTOL campaign uses a sequential study loop. Earlier [gripper](docs/studies/gripper.md) and [sensor](docs/sensor-gallery.md) studies remain reproducible.

</details>

<details>
<summary><strong>Run locally and verify</strong></summary>

Requirements: Linux, Docker, Node 22+ and uv. Keep API/Atlas credentials in the existing untracked server-side environment file.

```bash
uv sync --frozen
npm ci
npm ci --prefix sandbox/ui
docker compose --profile build build cad-image
docker compose --profile build build vtol-image
# Committed polars are already available; regenerate only for a new evaluator cohort.
# .venv/bin/python -m scripts.vtol_prepare
.venv/bin/python -m scripts.vtol_baseline
.venv/bin/python -m scripts.vtol_study --count 12
# Re-export existing records without new model calls:
.venv/bin/python -m scripts.vtol_study --export-only
npm run build
bash scripts/app_service.sh up
```

The service survives terminal closure. After rebuilding, run `bash scripts/app_service.sh down`, wait for it to finish, then run `bash scripts/app_service.sh up`.

The study resumes the same ID and $30 cap; changing the frozen evaluator or container image requires a new study ID. The existing global daily budget still applies. Open http://127.0.0.1:3215/vtol for the study, or use the configured Tailscale listener on port 8086. See [laptop access](docs/demo/README.md) and [Atlas setup](atlas/README.md).

```bash
.venv/bin/python -m pytest -q -m 'not integration'
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_vtol.py
npm run build
node_modules/.bin/playwright test tests/browser/vtol-gallery.spec.ts tests/browser/gripper-gallery.spec.ts tests/browser/sensor-gallery.spec.ts
```

</details>
