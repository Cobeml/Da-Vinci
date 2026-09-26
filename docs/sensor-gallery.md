# Sensor-mount gallery

The Next.js root page displays every recorded sensor-cradle attempt, its real GLB, mass, wall-strip stress/deflection estimates, and whether it improved the best passing mass. Each viewer has an independent Mount / On VTOL toggle, orbit/zoom controls, reset, and an expanded view. The original workbench remains at `/harness`.

The opening presentation section shows the lightest passing mount on the illustrative VTOL by default, beside the self-improvement methods and Atlas usage. Its expanded view preserves the selected mode. A link jumps to all chronological attempts below the overview.

## Research context

The methods section links to these primary sources (checked 2026-09-26):

- [Reflexion (Shinn et al., 2023)](https://arxiv.org/abs/2303.11366): 91% HumanEval pass@1 versus the cited 80% GPT-4 baseline. The agent stores linguistic reflections from task feedback for subsequent trials; this result includes iterative feedback, not a single unassisted generation.
- [Voyager (Wang et al., 2023)](https://voyager.minedojo.org/): 3.3 times as many unique Minecraft items as previous baselines. The complete system combines a retrieved executable skill library, iterative feedback and an automatic curriculum; the ratio does not isolate the skill library's contribution.
- [Self-Refine (Madaan et al., 2023)](https://arxiv.org/abs/2303.17651): approximately 20 percentage points average improvement across seven tasks over conventional one-step generation. Its feedback is model-generated; this harness additionally uses an independent geometry evaluator.

These are results for related methods in other domains, not validation of this CAD harness, guarantees of CAD performance, or controlled measurements of each mechanism's contribution to this study. No model weights are trained in the sensor study.

## Geometry and measurements

The new supported family is a 100 × 72 mm PA12 cradle with four 4.5 mm holes on an 80 × 52 mm pattern, two pivot walls, optional oval/triangular cutouts, base slots and gussets. Astra writes candidate CadQuery wrappers and selects parameters within this contract. The fixed family implementation is supplied by the harness; the agent does not invent an unrestricted topology or change its independent evaluator.

`sandbox/evaluate_sensor.py` reads only exported STEP and the fixed specification, verifies the solid against the family, measures volume/mass, and applies a conservative two-wall strip screen. Each wall carries half a 20 N lateral load at a 35 mm lever arm. The screen uses uninterrupted end webs, nominal E=1700 MPa and density=1.01 g/cm³, with no rib/gusset stiffness credit. Limits: 28 MPa stress, 0.65 mm deflection, 100 g mass. These are demo assumptions, not certified printed-material properties or FEA. Joint compliance, printing anisotropy, vibration and local stress concentrations are excluded.

The VTOL and sensor body are original procedural display models in `SensorViewer.tsx`. Their geometry is illustrative, not part of the tested assembly or mount mass. The orange mount uses the same evaluated GLB in both views and sits against the reference aircraft's mounting pad. No external model license is required.

## Live study and self-improvement

```bash
.venv/bin/python -m scripts.sensor_study --count 8
```

The fixed study ID resumes the same archive and **$3 total run cap**, including previous attempts. Completed iterations and saved responses are reused. The first six attempts optimize the family; two additional, explicit topology comparisons evaluate ribbed alternatives after convergence. All attempts remain visible. Lower mass counts as progress only when every fixed check passes.

After two evaluations, Astra writes a thickness utility and working policy. The harness runs four independent numeric cases and an invalid-input case before saving them. Subsequent generation receives actual executions of the saved tool, previous measured outcomes, accumulated lessons, and scoped Atlas Vector Search results. This demonstrates utility creation and context/policy reuse; it does not claim weight training or autonomous invention of the trusted evaluator.

The study reuses the existing Astra provider, atomic budget ledger, sandbox runner, Git repository, Atlas document store, Vector Search index and GridFS. New records live in `design_iterations` and `design_tools`; the run is diagnostic so it does not enter the legacy plate/wing queue. Memory uses the existing `memories` collection with a separate specification/evaluator cohort. **This bounded study executes sequentially from Python; the original Database Triggers continue to serve the full harness, not these new study collections.**

## Publishing and access

```bash
# Re-export completed records; no new model calls.
.venv/bin/python -m scripts.sensor_study --export-only
npm run build
bash scripts/dev.sh --production
```

The export writes `web/data/sensor-gallery.json` and hash-verified STEP/GLB copies to `web/public/models/sensor/`. Rendering the page needs no model call or database read. Restart the existing application only after the build finishes; avoid running two stacks on the same ports.

- Gallery: http://100.99.98.39:8086
- Full harness: http://100.99.98.39:8086/harness
- Existing Quarto report remains at http://100.99.98.39:8085

The existing `da-vinci-demo.service` user service forwards the private Tailscale address to Next.js. See `docs/demo/README.md` for startup after a host reboot.

## Verification

The published eight-attempt study reduced nominal mount mass from 83.535 g to 30.332 g (63.7%). All eight passed the fixed screen; the final two ribbed alternatives were heavier than the best oval-window design. Recorded API usage was approximately $0.77. These results demonstrate improvement within this parameterized family, not a controlled estimate of the causal benefit of any single memory or tool mechanism.

```bash
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_sensor.py
.venv/bin/python -m pytest -q -m 'not integration'
npm run typecheck
npm run build
node_modules/.bin/playwright test tests/browser/sensor-gallery.spec.ts
```

The CAD tests cover feasible lightweighting, excessive deflection and unsupported exported geometry. Browser checks cover all model cards, per-card mounting toggles, expanded views, absence of the old headline, mobile containment and actual STEP downloads.

Verified on 2026-09-26: two Docker/CAD tests, 19 non-integration Python tests, two gallery browser tests, and legacy navigation plus the two-worker replay/browser archive checks passed. TypeScript checking, Python lint and the production build passed. The running Tailscale endpoint returned the new page and all eight model references; its user service remained active.
