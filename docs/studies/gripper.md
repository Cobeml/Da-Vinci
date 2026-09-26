# Parallel-jaw gripper study

## Build plan

1. Freeze a three-part geometry contract: guide base and two symmetric sliding jaws. Each jaw has a fixed carriage/contact interface and an agent-designed graph of rectangular ribs.
2. Implement and independently test a 3D Euler–Bernoulli beam-frame solver. Evaluate pinch, payload, lateral and combined loads, nominal stress, contact displacement and compression buckling. Check exported STEP solids against the contract and actual BRep collisions at nine openings from 20 to 60 mm.
3. Run GPT-6 Astra with high reasoning and a larger output allowance, bounded by one $25 study budget. Archive proposals, failures, tool validations, policies, source commits and geometry through the existing Atlas/Git/GridFS services. Preserve all attempts and resume cached calls.
4. Generate a reusable member-sizing tool after initial feedback. Test it against independent analytic cases before reuse. Retrieve scoped prior outcomes with Atlas Vector Search and feed actual tool executions into later proposals.
5. Publish only after a passing candidate improves moving jaw mass by at least 15% over the conservative baseline. Replace the root gallery with interactive gripper models and opening controls; retain the sensor gallery at `/sensor`.

## Scope

This is a passive gripper mechanism study for an external opposed linear actuator. It does not design the motor, screw, controller or gripping-pad friction. The objective is moving jaw-pair mass; total three-part mass is reported separately. Nominal aluminium properties and ideal rigid beam joints are screening assumptions. The frame solver is not a continuum stress analysis of fillets, contacts or carriage bearings, and is not manufacturing certification.

All force cases act at the defined tip frame node (local x=8 mm, z=70 mm). Pad compliance and offset force couples are not modeled. Displacement means translation of that frame node. Stress is a conservative sum of axial and two bending contributions; local shear and torsional stresses are excluded. The beam solver includes axial, bending and torsional stiffness, with a rectangular-section torsion approximation.

The evaluator, load cases, geometry interfaces and acceptance limits remain fixed throughout the live study. The agent chooses rib connectivity, intermediate nodes, section sizes and extrusion depth within the declared domain; it does not rewrite its evaluator.

## Reproduce the study

```bash
# Requires configured Atlas/Astra credentials and the existing CAD Docker image.
# Resumes the same ID, cached model responses and $25 total budget.
.venv/bin/python -m scripts.gripper_study --count 8

# Re-export archived results without generating new designs.
.venv/bin/python -m scripts.gripper_study --export-only
npm run build
# Stop an existing app stack before restarting.
bash scripts/dev.sh --production
```

`davinci/gripper.py` freezes the evaluator cohort from the specification and solver/geometry source. Resuming refuses a changed evaluator. `scripts/gripper_study.py` uses the same Atlas budget ledger, artifact store, Git repository and vector index as the earlier study, with its own study/specification IDs. Candidate generation uses high reasoning and up to 14,000 output tokens; separate reflection calls use up to 6,000. The SDK's timeout is extended for these calls, and increased output allowances are reserved before each request.

The main route switches to the gripper gallery only if the export's measured improvement meets the publication threshold. `/sensor` preserves the eight-model sensor gallery; `/harness` retains the original multi-agent workbench. CAD and frame views display the same graph at the selected opening. Frame colors use the maximum nominal member stress across the four evaluated loads. The slider interpolates positions for display; collision validation samples nine positions, not every continuous configuration.

## Independent checks

- Analytic cantilever comparisons verify both bending axes, axial displacement and the pinned-member buckling formula.
- Docker CAD tests verify three solids, 0.30 mm running clearance at nine openings and exports of each actual STEP part.
- A thin single-column design fails stiffness screening; altered STEP geometry fails the reference check.
- The API budget test verifies that a larger reasoning/output request is rejected before network execution when its reservation exceeds the run cap.

```bash
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_gripper.py
.venv/bin/python -m pytest -q -m 'not integration'
node_modules/.bin/playwright test tests/browser/gripper-gallery.spec.ts tests/browser/sensor-gallery.spec.ts
```

## Completed result — 26 September 2026

Eight live Astra candidates were built, independently evaluated and archived. All passed the fixed screen. Iteration 7 is the minimum-mass passing design: 193.185 g for the moving pair versus 523.571 g baseline (63.1% reduction). Total three-part mass fell from 887.452 g to 557.066 g (37.2%). Its worst-case nominal stress is 77.109 MPa and tip displacement is 0.246344 mm; these are close to the 80 MPa / 0.25 mm screening limits. The less aggressive earlier designs remain visible for comparison.

The final alternative was slightly heavier at 193.266 g and did not replace the best design. All nine sampled clearances are 0.30 mm. Vector retrieval returned prior study records, and the saved sizing tool was invoked before iterations 3–8. A review-agent call after every evaluation produced an archived next-step policy. These are observations of one bounded study, not a controlled causal estimate of any one improvement mechanism.

Recorded API accounting was $4.39, including a conservative reservation charged for one request that timed out. The last iteration resumed under the same budget with a longer timeout. The agent was not given a different evaluator or relaxed acceptance limits for that retry.

The three gripper checks (analytic solver, real CAD/travel/weak-design rejection, forged-STEP rejection) and 21 non-integration Python tests passed. The production frontend build and browser checks cover jaw controls, frame views, expanded models, STEP downloads, responsive layout and the preserved sensor gallery. Exact records and measurements are in `web/data/gripper-gallery.json`; the public GLB and STEP assets are exported from the archived artifacts.
