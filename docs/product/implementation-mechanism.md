# MuJoCo mechanism implementation record

Added optional `mujoco-slider` through the existing registry, capability assessment, trusted execution service, artifact manifests, public lifecycle and installed UI presentation. There is no second worker or alternative acceptance engine. Candidate/evaluator code cannot supply MJCF, trusted scores, mass or inertia. The current CAD builder contract still returns a CadQuery assembly exported to STEP.

The supported task and public `SliderSettings` contract are documented in [mechanism simulation](mechanism-simulation.md). The scope is one ideal vertical slider, two homogeneous rigid bodies and frictionless soft normal contact. Coordinate conversion, collision assumptions, loads, controller, trajectory and numerical settings are fixed before candidate submission. XML decks are downloadable artifacts; existing localhost attachment protections remain intact.

The native reference audit found that 1 ms contact timesteps did not meet the fixed 0.1 mm trajectory-sensitivity contract. The example now starts at 0.25 ms and tests two further halvings; a coarse-step numerical-failure regression preserves the failed case. An equilibrium threshold equal to its declared uncertainty was corrected during draft/reference development to avoid classifying roundoff as physical failure. No frozen or historical acceptance suite was modified. Reference verification supplies independently specified bounds for **all** metrics, including the [0,0.4] N actuator range rather than using observed peak-force answers.

Resources are estimated from the actual scenario duration/timestep. Runtime limits use the same bounded Docker execution and cancellation path as other adapters. Solver step/timing/RSS measurements are archived separately from host-owned `resources.json`, so the runner cannot overwrite the solver's estimate feedback. Independent BRep inspection and solver reimport both check semantic assembly bindings.

## Compatibility and packaging

This is additive: no database migration, mandatory host solver dependency, model provider or cloud service. Existing legacy screening evaluators retain their formulas. Adding an adapter and trusted execution source changes the suite execution identity: old frozen v2 experiments remain inspectable, but resumed execution requires a linked plan revision and reference verification under the new identity. Archived studies, evidence and scores are unchanged.

`davinci setup --template mujoco` installs the optional pinned image. The descriptor and `SliderSettings` schema are available without importing MuJoCo. The installed package includes the adapter, solver source, walkthrough, JSON schema, Dockerfile and docs. External users use the ordinary localhost service; managed deterministic tests use the existing fixture-server option `--fixture mechanism`. Automatic free-form mechanism authoring is not claimed.

## Reproduction

```bash
uv run davinci setup --template mujoco
uv run pytest -m 'not integration' -q
uv run python scripts/required_native.py --mechanism
uv run python scripts/run_methodology_benchmark.py --suite mechanism \
  --workspace runtime/mechanism-validation --output runtime/mechanism-validation-results
npm run build:ui
uv build --no-build-isolation
uv venv /tmp/davinci-mechanism-wheel
uv pip install --python /tmp/davinci-mechanism-wheel/bin/python dist/*.whl
cd /tmp
/tmp/davinci-mechanism-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_methodology.py \
  --suite mechanism --workspace /tmp/mechanism-installed --output /tmp/mechanism-installed-results
```

Use a fresh workspace for a separate campaign. The required native gate fails on missing images or skipped required checks. CI builds this optional runtime in its own job, runs native references and both drivers, and repeats the public journey from a fresh wheel outside the checkout with no host MuJoCo installation. Fixture reasoning is distinguished from real native physics. Live spending stays disabled.

Validation completed on 2026-10-02:

- **185 fast tests passed**, 47 integration tests deselected. The discovery assertion was extended to require `mujoco-slider`; artifact path/content/integrity checks were preserved.
- **7 required MuJoCo native checks passed**, six fast tests deselected. These cover analytical CAD mass/COM/inertia, simple motion, contact/equilibrium, conservation, timestep sensitivity, coarse-step numerical failure, ambiguous/misplaced assemblies and both full public routes. No required MuJoCo check was skipped.
- Existing required gates: **12 CAD/route/tool tests passed** (one explicitly opt-in paid-model test skipped), and **11 structural tests passed** without skips.
- Fresh installed wheel outside checkout: both public mechanism routes passed with no host MuJoCo dependency, complete source/runtime/artifact provenance, schema discovery, repeated final evaluation and cross-driver metric/contract agreement. Neither route made paid calls.
- Ruff, UI/docs build, wheel/sdist build and `git diff --check` passed.

[Recorded results](https://github.com/Cobeml/Da-Vinci/blob/master/docs/product/mechanism-results.json) include the tested image `sha256:531186d65f0b91991f40d3c66dea7b427e645885ca0235de506d8a6f25497435`, physical-contract identity and full report checksums. Reports are retained in `runtime/mechanism-validation-results`; the raw installed-workspace evidence is archived in `runtime/mechanism-installed-archive` with its original scope intact. Reproduce a new campaign rather than relabeling archived workspace identities.

Both routes measured a 64.8 g solid carriage failing the lift, two invalid assembly candidates with incomplete evidence, and a 30.5856 g pocketed carriage passing under the same 0.4 N actuator/loads/criteria. Moving mass fell **52.8%**. Final nominal tracking error was about 4.75e-16 m; settled penetration was 4.4388e-6 m; peak actuation was 0.326131 N. The trajectory-sensitivity allowance actually measured was 9.0563e-5 m, with an additional declared nominal position allowance of 1e-4 m; the near-zero nominal tracking value is not a precision or real-world accuracy claim. Two fresh evaluations and both drivers agreed within the predeclared 1e-8 tolerances. This is a scripted geometry improvement for a rigid-slider task, not autonomous model quality or structural adequacy. No physical laboratory observations or live model calls are part of this evidence. Fluid, fatigue, thermal and other new domain packages remain deferred pending their own task, scope and reference suite.
