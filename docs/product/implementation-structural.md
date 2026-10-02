# Structural adapter implementation record

Implemented after product phases 1–6, 2026-10-01. Public contracts and exact applicability are in [structural simulation](structural-simulation.md). Core implementation commit: `421bf9c`.

## Decisions and compatibility

- Added the optional `calculix-static` adapter through the existing registry, lifecycle and sandbox worker. No parallel engine, database migration, cloud service, default host solver dependency or model call was introduced.
- Trusted source creates the solver deck from frozen `StructuralSettings`, actual STEP and independently checked regions. Candidate hints and authored evaluator code cannot supply structural measurements or modify the solver. Adapter/contract/solver source participates in execution identity; previously frozen v2 suites remain viewable but need a linked revision and verification to run against changed code. Historical and legacy screening evidence is unchanged.
- Gmsh 4.15.2 and source-built CalculiX 2.23/SPOOLES 2.2 run in the optional CPU Docker image. The tested image ID is `sha256:c217125841f2f6af494feb4e9415c25c06c3775e5776480dd4c762eb1da5f458`. Independent builds can have different image IDs.
- Fixed support/load semantics, gauge placement, uncertainty, refinement and hard limits precede generation. Five mesh levels were declared for the final example after a development study failed convergence at four; no frozen engineering limit was relaxed.
- Both public drivers use the same evaluator service. Independent authoring retains independent verification provenance. Managed adoption additionally demonstrates exact frozen-suite preservation and a fresh final rerun.

## Measured bracket result

The baseline has a shelf, mounting wall and two through holes. The revision adds two tapered ribs; it changes more than thickness. Both use the same 20 N load, material, interfaces, stress gauge, 0.1 mm hard displacement limit and convergence policy.

| Measured quantity | Baseline | Ribbed revision | Change |
| --- | ---: | ---: | ---: |
| Loaded-face displacement (mm) | 0.177657 | 0.012949 | −92.7% |
| Predeclared gauge-mean von Mises (MPa) | 5.94224 | 1.05184 | −82.3% |
| CAD-derived mass (g) | 18.30457 | 22.97017 | +25.5% |
| Evidence complete | yes | yes | |
| Accepted under stated tests | no | yes | |

External, independently authored managed-fixture and exact-suite managed adoption produced matching values (comparison tolerance 1e-7 absolute / 1e-8 relative). The reported displacement numerical errors are 0.001856 / 0.0000621 mm, with separate declared 5% nominal uncertainty allowances. The full table and identities are recorded in the checkout's `docs/product/structural-results.json`; the full local ledger and solver artifacts were preserved in ignored `runtime/structural-validation/`. That workspace can be opened with:

```bash
uv run davinci --workspace runtime/structural-validation serve --no-browser
```

The stress measure is a predefined volume mean, not peak strength or fatigue qualification. The uncertainty allowance and empirical convergence diagnostic are not guaranteed real-world error bounds. A deterministic model fixture demonstrates orchestration; real Gmsh/CalculiX execution supplies the physics evidence. Arbitrary natural-language structural test authoring is not claimed: automatic authoring retains the existing analytic beam recipe; managed structural iteration can adopt an independently verified suite.

## Checks actually run

| Check | Command | Result |
| --- | --- | --- |
| Fast regression | `uv run pytest -m 'not integration' -q` | 158 passed, 39 deselected |
| Required structural native gate | `uv run python scripts/required_native.py --structural` | 11 passed, 6 deselected; no skips |
| Existing required native gate | `uv run python scripts/required_native.py` | 11 passed, 1 opt-in live-model test skipped, 41 deselected |
| Installed wheel, outside checkout | command below | Keyless public external route: real CAD, references, failed candidate, revision and accepted report |

The structural gate includes exact axial displacement/stress/mass, independently specified beam references, physical failure, varied-feature bracket improvement, disconnected geometry, incorrect normals, invalid gauge placement, mesh resource exhaustion, insufficient convergence, false geometry declarations and both public drivers. Fast checks cover dimensional conversion, unavailable resources, unsupported physics/material/runtime and setup validation. Existing shared tests cover cancellation and bounded/corrupt artifacts. CI requires the optional solver image and fails instead of skipping the required structural gate.

Installed-package reproduction (after building the optional runtime):

```bash
node scripts/build_product_ui.mjs
uv run python -m build --outdir /tmp/davinci-structural-dist
uv venv /tmp/davinci-structural-wheel
uv pip install --python /tmp/davinci-structural-wheel/bin/python /tmp/davinci-structural-dist/da_vinci_harness-0.2.0-py3-none-any.whl
cd /tmp
/tmp/davinci-structural-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_structural.py
```

The fresh environment has no host Gmsh or NumPy. The check clears model/database credentials, starts the installed workspace service and uses public HTTP operations. Package schemas, optional runtime recipe and rendered scope documentation are checked. No paid/live model call, Atlas/private database or physical hardware measurement ran. The existing Starlette/httpx deprecation warning remains. No browser UI code changed in this phase; the browser suite was not rerun.

## Complete external journey

```bash
davinci init structural-workspace --driver external --template custom
cd structural-workspace
davinci setup --template structural
davinci service ensure
python -m davinci.product.structural.walkthrough --workspace . --report structural-report.json
```

For the deterministic managed journey and exact-suite handoff, run `DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_structural.py -m integration -k public_driver_parity -q` from the checkout with the structural image installed. This uses public author/proposal/reflection operations and the normal worker; it does not fabricate trusted scores.
