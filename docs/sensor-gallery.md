# Sensor-mount gallery

The Next.js root page displays every recorded sensor-cradle attempt, its real GLB, mass, wall-strip stress/deflection estimates, and whether it improved the best passing mass. Each viewer has an independent Mount / On VTOL toggle, orbit/zoom controls, reset, and an expanded view. The original workbench remains at `/harness`.

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

```bash
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_sensor.py
.venv/bin/python -m pytest -q -m 'not integration'
npm run typecheck
npm run build
node_modules/.bin/playwright test tests/browser/sensor-gallery.spec.ts
```

The CAD tests cover feasible lightweighting, excessive deflection and unsupported exported geometry. Browser checks cover all model cards, per-card mounting toggles, expanded views, absence of the old headline, mobile containment and actual STEP downloads.
