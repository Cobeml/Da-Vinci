# Da Vinci: Recursive Improvement CAD Harness

A CAD harness for physical engineering tasks, built for the MongoDB Atlas Hackathon. GPT-6 Astra edits designs, invokes engineering tools, reviews independent evaluations and carries lessons into later attempts. Model weights stay fixed.

The latest experiment optimizes a streamlined lift-and-cruise VTOL using **CST airfoils, spline-lofted CAD and aerodynamic tools**. A matched control uses dimensional edits alone. Both start from the same hollow aircraft with a **150 Wh battery and 0.5 kg payload**; speed, payload capacity, mass and endurance are benchmarked alongside range.

**Stack:** Next.js / React · Python · CadQuery / OpenCascade · GPT-6 Astra · MongoDB Atlas · AeroSandbox · NeuralFoil · XFOIL

[Interactive geometry-tool experiment](http://100.99.98.39:8086/vtol-tools) · [Methods and research](docs/studies/vtol-surface-tools.md) · [Results](docs/studies/vtol-surface-results.md) · [Previous VTOL study](http://100.99.98.39:8086/vtol)

## Self-improvement methods

1. **Edit continuous geometry.** The agent changes CST section coefficients, three-section wings, a hollow fuselage and fairings. The tools build and export actual STEP solids.
2. **Use engineering tools.** `analyze_sections` computes lift, drag and pitching moment. `optimize_sections` searches airfoil coefficients under thickness, lift, moment and confidence constraints. Validated tool implementations are saved for reuse.
3. **Reflect and retry.** Range, trim, packing and structural results guide later designs. Failed edits return errors and preserve the last valid geometry. Policies, tool calls and failed attempts stay in the archive.

The full harness also supports agent-written Python tools and gated orchestration/policy changes. This experiment tests an engineered tool package with a frozen evaluator; the agent does not rewrite scoring physics during the comparison.

## MongoDB Atlas

- **Documents** archive geometry specifications, evaluations, tool calls, policies and budgets.
- **Vector Search** retrieves prior results separately for each arm and evaluator version.
- **GridFS** stores STEP and interactive 3D artifacts.
- **Database Triggers** enqueue evaluation and reflection in the full two-specialist workbench. This controlled study uses a resumable sequential proposal loop, followed by bounded parallel finalist checks.

## Improvement by model

**Screening range:** 70.9 km baseline → 76.0 km with dimensional controls (**7.3%**) and 74.4 km with surface tools (**5.0%**). These use one frozen evaluator; the previous VTOL study is a separate comparison.

**Verified range:** 71.2 km baseline, 77.2 km dimensional controls, 74.4 km surface tools. Verified gains over the baseline are **8.4% for dimensional controls** and **4.4% for surface tools**. The surface-tool arm changes verified range by **-3.7% relative to the control**.

No new-tool design passed all promotion gates. The experiment is published at `/vtol-tools`; the previous validated study remains on the homepage.

| Verified design | Range est. (km) | Max speed est. (m/s) | Payload capacity est. (kg) | Endurance est. (min) | Mass (kg) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 71.2 | 19.00 | 0.816 | 87.0 | 3.87 |
| Dimensional controls | 77.2 | 19.00 | 0.816 | 97.5 | 3.86 |
| Surface tools | 74.4 | 17.00 | 0.816 | 94.0 | 3.98 |

| Iteration | Dimensional range est. (km) | Result | Surface-tool range est. (km) | Result |
| --- | ---: | --- | ---: | --- |
| 1 | 70.9 | passed | 70.9 | passed |
| 2 | 70.9 | passed | 76.7 | failed |
| 3 | 0.0 | failed | 72.4 | passed |
| 4 | 72.3 | passed | 72.6 | passed |
| 5 | 72.4 | passed | 72.7 | passed |
| 6 | 72.6 | passed | 72.8 | passed |
| 7 | 74.6 | passed | 72.5 | passed |
| 8 | 75.4 | passed | 72.3 | passed |
| 9 | 76.0 | passed | 72.8 | passed |
| 10 | 75.9 | passed | 72.6 | passed |
| 11 | 76.0 | passed | 72.8 | passed |
| 12 | 76.0 | passed | 74.4 | passed |

- **Best dimensional design, iteration 12:** Reduced shell thickness from 1.25 to 1.20 mm while retaining the 2.50 m wing, 125 mm tail chord and 32.5 mm spar.
- **Best surface-tool design, iteration 12:** Increased washout from −1.00° to −1.25°, reduced spar wall thickness from 1.05 to 1.00 mm and reduced tail span from 620 to 580 mm. Retained the seed root section and the optimized tip section.

The dimensional winner increases span from 2.30 to 2.50 m, narrows the body from 170 to 140 mm and lowers its height from 180 to 150 mm. The surface-tool winner also reaches 2.50 m span, changes the tip CST section, increases middle-wing chord by 4% and adds 0.2° middle-station twist; the root section stays unchanged. Its screening mass is 3.98 kg versus 3.86 kg for the dimensional winner. These are observed design differences, not an isolated causal attribution of the range gap.

24 scored entries, including the shared baseline in each arm. 42 non-submission tool calls, 7 returned errors, and 14,757 reported successful section-optimizer evaluations. Recorded API accounting: **$11.00 / $60**, including both pilot attempts. Numerical solver time is separate from API accounting.

The tools are usable in the agent workflow, but this run does not demonstrate a range advantage over dimensional editing. Keep them available for geometry exploration; do not describe the package as a proven performance improvement. A useful next experiment would derive section-optimizer conditions from current aircraft trim, include whole-aircraft mass and speed penalties, and choose parent designs that retain the required speed and payload. Those changes need a new matched campaign; they were not retroactively applied here.

<details>
<summary><strong>Agent harness, geometry tools and verification</strong></summary>

The agent calls `edit_geometry`, `analyze_sections`, `optimize_sections` and `submit_design`. The control has only dimensional editing and submission. Each proposal permits six responses. A live pilot checks profile editing, wing-station editing and recovery from an invalid request. Both arms share the model, mission, constraints and evaluation code, with separate histories and Atlas retrieval filters.

CadQuery builds smooth B-spline lofts from CST sections and elliptical body stations. The evaluator checks STEP consistency, solid validity, spar containment, battery/payload fit and rotor clearance. Component mass and balance include the shell, foam, skin, fairings, spars and hardware.

Screening uses AeroSandbox lifting-line with geometry-dependent NeuralFoil section aerodynamics. Finalists solve nonlinear circulation, lift balance and pitching-moment balance together at two resolutions. Static margin uses implicit flow derivatives. XFOIL checks section consistency near actual operating points. Measured UIUC propeller maps connect drag and thrust to power and mission range.

The mission deducts 90 seconds of hover and 40 seconds of transition allowance, with 20% battery reserve. Payload capacity requires a supported 10 km mission and is sampled in 0.048 kg increments. Adverse cases use 10% less energy, 20% more total drag and 10% more empty mass.

A new-tool winner needs at least 5% verified range gain over both baseline and control, at least 95% of baseline speed and payload, an adverse-case advantage, XFOIL consistency and ≤2% range change on refinement. All attempts remain visible. Source hashes, container digest, responses, geometry and API accounting support resumption and audit.

</details>

<details>
<summary><strong>Research and limitations</strong></summary>

[August 2026: natural-language-driven airfoil design](https://www.iisci.net/zh/article/doi/10.16356/j.2097-6771.2026.04.008/) describes LLM/CST workflows including long-endurance UAV design. The accessible abstract supports feasibility; no transferable performance percentage is assumed.

[NeuralFoil](https://github.com/peterdsharpe/NeuralFoil) provides fast section predictions. [AeroSandbox nonlinear lifting-line](https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/nonlinear_lifting_line/) supports whole-wing interaction and trim. [CadQuery](https://cadquery.readthedocs.io/en/latest/classreference.html) supplies spline, loft and STEP operations. [XFOIL](https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt) provides consistency with NeuralFoil's training solver, not independent experimental evidence. Propulsion uses [UIUC measurements](https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html).

CST gives the agent a compact, physically meaningful section interface. General NURBS control nets and [FFD](https://mdolab-pygeo.readthedocs-hosted.com/en/latest/advanced_ffd.html) need additional topology and internal-interface preservation. Full-body [SU2 optimization](https://su2code.github.io/tutorials/Multi_Objective_Shape_Design/) is deferred until meshing and CFD are independently verified.

Results are engineering estimates, not flight tests. The lifting-line model interpolates section stations; it is not a CFD mesh of the STEP surface. The evaluator does not resolve body separation, body lift/moment, wing/body interference, rotor interaction, dynamic transition, flutter, fatigue, joints or local shell buckling. Fairings receive no assumed interference-drag benefit. NeuralFoil confidence is a screening signal, not a calibrated probability of correctness. The comparison tests the complete tool package with extra numerical optimization, not equal compute or each self-improvement method's isolated contribution.

</details>

<details>
<summary><strong>Previous VTOL result: 24.6% estimated range improvement</strong></summary>


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


</details>

<details>
<summary><strong>Run locally and verify</strong></summary>

Requirements: Linux, Docker, Node 22+ and uv. Credentials stay in the existing untracked server-side environment file. Never print them. The experiment uses the existing `da-vinci-vtol:local` image and pins its digest when the study starts.

```bash
uv sync --frozen
npm ci
# For a fresh workspace, build the CAD and VTOL images first.
docker compose --profile build build cad-image
docker compose --profile build build vtol-image
# Initialize once; do not regenerate a running study's seed.
.venv/bin/python -m scripts.surface_prepare seed
.venv/bin/python -m scripts.surface_prepare evaluate
.venv/bin/python -m scripts.surface_study --count 12
# Re-export archived results without model calls:
.venv/bin/python -m scripts.surface_study --export-only
node scripts/surface_assets.mjs
npm run build
bash scripts/app_service.sh up
```

The study resumes the same ID and three budget ledgers: $6 pilot, $27 control and $27 surface tools. Scored designs freeze the geometry/evaluator/image identity. Restart the existing service after rebuilding: run `bash scripts/app_service.sh down`, wait for completion, then `bash scripts/app_service.sh up`.

Open http://127.0.0.1:3215/vtol-tools locally or http://100.99.98.39:8086/vtol-tools from the connected Tailscale laptop. See [laptop access](docs/demo/README.md) and [Atlas setup](atlas/README.md).

```bash
.venv/bin/python -m pytest -q -m 'not integration'
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_surface.py
npm run build
node_modules/.bin/playwright test tests/browser/surface-gallery.spec.ts tests/browser/vtol-gallery.spec.ts tests/browser/gripper-gallery.spec.ts tests/browser/sensor-gallery.spec.ts
```

The [full workbench](http://100.99.98.39:8086/harness), [gripper](http://100.99.98.39:8086/gripper) and [sensor](http://100.99.98.39:8086/sensor) studies remain available.

</details>
