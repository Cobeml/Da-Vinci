# Lift-and-cruise VTOL range study

The campaign compares twelve complete small survey aircraft designs at a fixed 0.5 kg payload, 150 Wh battery, sea-level atmosphere and zero wind. It optimizes estimated cruise range while retaining at least 95% of baseline supported maximum speed and 10 km mission payload capacity. The API cap is $30; global budget limits remain active.

## Build sequence

1. Freeze sourced propeller maps, generated XFOIL polars, hardware assumptions and a feasible CAD baseline.
2. Validate STEP geometry independently, calculate component mass/CG, VLM trim and induced drag, viscous/body drag, propulsion and mission energy, and beam structural screens.
3. Run the baseline and eleven Astra proposals with memory retrieval, independently tested generated utility and review-agent policies.
4. Recheck baseline/top three at finer VLM resolutions and compare paired adverse assumptions.
5. Publish the VTOL gallery; promote it to the homepage only above 10% nominal range improvement with positive combined-adverse improvement and capability retention.

## Fixed assumptions

`vtol_spec.py` is the authoritative frozen specification. Propeller thrust/power coefficients are wind-tunnel measurements from UIUC; hardware masses, motor/ESC efficiencies, power caps, battery characteristics and structural allowables are engineering assumptions. CAD dimensions are millimetres; physics uses SI. External surfaces, hollow shell, foam wing/tail, spars and booms have separate material properties. Motors, battery, avionics and payload use explicit inventories; empty space is not solid material.

Cruise range excludes distance during takeoff/transition, deducts 90 seconds hover plus 40 seconds at 1.15 times hover power and leaves 20% energy reserve. It is total distance, not radius. Maximum speed means highest passing supported point on the 0.25 m/s sweep; unsupported propeller conditions are not extrapolated. Payload capacity varies density in the fixed bay and requires the 10 km mission, hover reserve, CG, trim, structural and gross-mass limits to pass.

There is no full-aircraft CFD, dynamic transition, rotor interaction, flutter, fatigue or closed-loop controller simulation. Beam checks do not certify joints or local shell buckling. Sensitivity cases are scenarios, not confidence intervals or flight validation. The agent cannot rewrite the evaluator, increase battery energy, remove required payload or change hardware.

## Sources

- [UIUC measured APC propeller data](https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html): APC 16×8 static lift maps and 12×8 cruise maps. Raw files and SHA-256 provenance are archived in the repository.
- [AeroSandbox VLM](https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/vortex_lattice_method/): lift, moments, induced drag and stability.
- [XFOIL](https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt): NACA 2412/0012 viscous polars, Reynolds 100,000–1,000,000, Ncrit 9. Source archive checksum is pinned in the Dockerfile.

## Reproduction

```bash
docker compose --profile build build vtol-image
.venv/bin/python -m scripts.vtol_prepare
.venv/bin/python -m scripts.vtol_baseline
.venv/bin/python -m scripts.vtol_study --count 12
.venv/bin/python -m scripts.vtol_study --export-only
```

Freeze the evaluator only after baseline validation. Changing its source, data or specification requires a new study ID. The sequential campaign reuses Atlas/GridFS/Vector Search; the existing workbench's Database Triggers do not drive this study.

While proposals run, `.venv/bin/python -m scripts.vtol_refine_baseline --iteration 7` can precompute the two finer checks for an already archived iteration (omit the option for the baseline). It makes no API or Atlas calls and writes the same cached evidence used by finalist validation.

## Implementation notes

The pitch control is an all-moving horizontal tail. VLM samples its incidence directly; the solver does not implement the flap metadata used during the first setup probe. The six-point lift/moment/induced-drag response surface provides a fast trim sweep. Profile drag uses XFOIL at matching Reynolds number and interpolated section lift; body/pod/boom drag uses the documented empirical buildup. These are engineering approximations, not a resolved wake model.

The XFOIL source is compiled in double precision without debug floating-point traps. Polars accumulate in memory and export once, avoiding a legacy Fortran append-at-EOF error. The twelve committed tables contain only converged rows. The container image digest, source/data fingerprint and fixed spec identify the evaluation cohort.

Three meshes are used: 10 spanwise panels per section for the campaign, then 14 and 18 for baseline/top-three checks. Promotion requires less than 3% change in range, supported maximum speed and best-range drag between the two finer resolutions. All nominal per-iteration metrics remain from the same campaign grid; finer-grid evidence is archived separately.

Empty/truncated model outputs are retained and retried with up to 32,000 output tokens; their cost remains in the original ledger. No retry changes the evaluator or the $30 cap. The energy utility is checked on four numeric cases and four invalid-input cases before reuse.

## Superseded first campaign

The first twelve-design campaign is retained in Atlas and [the audit export](vtol-v1-audit.json), but its performance claims are withdrawn. Final visual/geometry review found that constant-diameter spars protruded from thinner wing tips while the aerodynamic model assumed an uninterrupted airfoil. The corrected v2 cohort uses tapered, contained spars following the quarter-chord mean line, integrates bending compliance along the changing section, and independently checks BRep containment and material-volume conservation. Earlier results are not mixed into its ranking.

The two campaigns share a total $30 API allowance. The corrected campaign receives only the unspent remainder after the first campaign's $10.92388498 cost. The UI reports their combined accounting.
