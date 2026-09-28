# Streamlined VTOL: matched geometry-tool experiment

This study compares existing dimensional controls with CST airfoils, three-section spline wings and a constrained section optimizer. Both arms use the same smooth, hollow fuselage, wing-root fairings, covered booms, mission and evaluator. The previous study remains archived and is not a direct numerical control.

## Geometry and tool interface

`GeometrySpec` version 1 contains `dimensions`, `root`, `tip`, and `shape`. Each airfoil contains eight upper and eight lower CST weights, a leading-edge modifier and trailing-edge thickness. Middle-section coefficients interpolate between root and tip. A middle-chord edit preserves the straight quarter-chord planform line. Body shaping uses seven ordered elliptical stations.

The agent uses `edit_geometry`, `analyze_sections`, `optimize_sections`, and `submit_design`. Control-arm editing accepts only dimensions. Tool calls return actual computed results and actionable failures; invalid edits preserve the previous geometry. Successful edits produce a valid STEP round trip and a GridFS preview. The optimizer is bounded to 200 iterations and 180 seconds. It optimizes three operating conditions with lift, thickness, camber, pitching-moment and confidence constraints.

The sandbox checks spar containment and actual battery/payload cavity fit. The independent evaluator compares the submitted STEP solids against the canonical geometry and checks rotor clearances. Foam, skin, shell, spar, fairing and fixed hardware masses contribute to mass and balance.

## Physics

Screening uses AeroSandbox lifting-line with actual CST sections and NeuralFoil section forces and moments. Reynolds-dependent cubic tables support trim over an attached-flow domain: aircraft angle of attack −2° to 8°, tail adjustment −5° to 5°, and airspeed 10–30 m/s. No extrapolation outside that domain is accepted. Direct solves audit the range optimum, maximum-speed boundary, adverse optimum and payload-capacity condition.

Finalists use nonlinear lifting-line at two spanwise resolutions (8 and 12 panels per section). Circulation, aircraft angle of attack and tail setting are solved together at each actual mission condition. The linear table supplies an initial guess only. Implicit flow derivatives determine static margin; unsupported roots are excluded. The nominal optimum is also checked with AeroSandbox's original nonlinear solver. Fixed-angle audit solves receive one cold-start retry after a failed warm start. Containers retain network isolation and bounded resources; nonlinear verification permits 12 GB memory for differentiated flow equations.

Payload capacity is sampled in 0.048 kg increments and requires at least one supported cruise condition covering the fixed 10 km mission. Adverse cases reduce battery energy by 10%, increase total drag by 20%, increase empty mass by 10%, and combine those changes. XFOIL checks root and tip predictions near the actual operating conditions. This is consistency with NeuralFoil's training solver, not independent experimental evidence.

Body drag uses measured CAD wetted area with a conservative empirical form factor. No wing/body interference discount is assigned to fairings. Wing panel loads add a bending screen to the existing conservative distributed-load beam check. Propulsion uses the same UIUC experimental propeller maps as the previous study. Battery, payload, reserve, hover and transition assumptions remain fixed.

These are engineering estimates. Full-aircraft viscous CFD, body lift/moment, separated flow, rotor interaction, dynamic transition, joints, buckling, flutter, fatigue and flight control are not resolved. The airfoil confidence threshold is not a calibrated probability of physical correctness.

## Experiment and accounting

- Three-task live pilot: profile edit, middle-wing edit, and recovery from an intentionally invalid thickness request.
- Up to 12 scored designs per arm, including one shared baseline; alternating proposal rounds.
- Same configured Astra model and reasoning setting; separate histories and Atlas Vector Search filters.
- API caps: pilot $6, control $27, surface tools $27. Numerical optimization effort and tool time are reported separately.
- Freeze geometry/evaluator source hashes, container digest and seed before paid runs. Cache evaluations by these identifiers and solver settings. Save model responses before executing tools so resuming does not repeat completed API requests.
- A new winner requires at least 5% verified range gain over both seed and control, at least 95% of baseline speed/payload, positive adverse-case gain, successful section checks and ≤2% range change on refinement.

The treatment is the complete tool package, not an equal-compute comparison or an isolated causal estimate of CST. The agent's stored policy evolves from earlier evaluations; the scoring physics does not change mid-campaign. Database Triggers continue to drive the separate full workbench; this study has a resumable sequential runner.

## Reproduce

Use the existing project environment and `da-vinci-vtol:local` container. Credentials are loaded by the live runner; never print them.

```bash
.venv/bin/python -m scripts.surface_prepare seed
.venv/bin/python -m scripts.surface_prepare evaluate
.venv/bin/python -m scripts.surface_prepare evaluate --nonlinear --resolution 8
DAVINCI_INTEGRATION=1 .venv/bin/python -m pytest -q tests/test_surface.py
.venv/bin/python -m scripts.surface_study --count 12
```

Do not regenerate the seed or edit frozen evaluation files during a campaign. The runner refuses to resume when their identities change. `--export-only` republishes archived results; `--validate-only` runs finalist validation. `--pilot-only` spends only within the pilot allocation. Live results are exported to the Next.js `/vtol-tools` route; homepage promotion is conditional on the validation gate.

## Research and implementation references

- [August 2026: natural-language-driven airfoil design with LLM/CST workflows](https://www.iisci.net/zh/article/doi/10.16356/j.2097-6771.2026.04.008/). The accessible abstract supports feasibility; no transferable improvement percentage is assumed.
- [NeuralFoil implementation and benchmarks](https://github.com/peterdsharpe/NeuralFoil).
- [AeroSandbox nonlinear lifting-line](https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/nonlinear_lifting_line/).
- [CadQuery spline/loft/STEP interfaces](https://cadquery.readthedocs.io/en/latest/classreference.html).
- [OpenAI function-calling workflow](https://developers.openai.com/api/docs/guides/function-calling).
- [pyGeo FFD workflow](https://mdolab-pygeo.readthedocs-hosted.com/en/latest/advanced_ffd.html): deferred because mesh deformation does not automatically preserve valid CAD solids or internal interfaces.
- [SU2 shape optimization](https://su2code.github.io/tutorials/Multi_Objective_Shape_Design/): deferred pending a separately verified full-body meshing and CFD workflow.
