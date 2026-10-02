# Methodology benchmark

This benchmark distinguishes deterministic orchestration, native simulation, attributed observations and live-model quality. Passing one category is not evidence for the others. [Recorded native results](https://github.com/Cobeml/Da-Vinci/blob/master/docs/product/methodology-results.json) include versions, image identities, counts, failures, costs and report checksums. Full reports and CAD/solver artifacts are produced in the selected workspace on reproduction and retained as CI artifacts.

## Reproduce both drivers without model credentials

From a source checkout with the [development environment](development.md) installed:

```bash
uv sync --extra studies --frozen
uv run davinci setup --template custom
uv run davinci setup --template structural
uv run python scripts/run_methodology_benchmark.py \
  --workspace runtime/methodology-new --output runtime/methodology-new-results
```

The script starts one localhost service with the ordinary Engine/worker and explicit deterministic reasoning, clears credential inputs, then executes both routes through supported HTTP operations. Missing CAD/structural images fail the command; physics is not mocked. Use a **new workspace** for a new campaign; an operation conflict never silently resets existing evidence. On failure, retain the workspace and inspect job/status evidence before deciding to resume or run a separate campaign.

For separate installed-package sessions, terminal one:

```bash
python -m davinci.product.benchmark_server --workspace ./methodology-workspace
```

Terminal two, external coding-agent script:

```bash
python -m davinci.product.methodology --workspace ./methodology-workspace \
  --driver external --output ./evidence-external --operation external-trial-1
```

Then managed deterministic author/proposal/reflection fixture:

```bash
python -m davinci.product.methodology --workspace ./methodology-workspace \
  --driver managed --output ./evidence-managed --operation managed-trial-1
```

This fixture server is for deterministic testing, not live reasoning. External requests cannot construct its provider. The managed fixture uses public staged author/propose/reflect operations; automatic natural-language orchestration is separately tested in `test_managed.py` and the installed route check. Neither route calls a paid model. `--skip-structural` explicitly runs a partial benchmark; it does not establish structural capability. The installed default requires only the Python package; native solver software stays in optional containers.

## Requests, controls and metrics

The fixed request set contains a perforated structural bracket with a ribbed revision, an edit that deliberately violates a fixed length/root regression constraint, an invalid evaluator followed by a linked correction and repeated reference verification, an unavailable fatigue request, an over-capacity test, and two later related beam tasks. The structural case uses actual STEP-derived Gmsh/CalculiX execution; beam cases use actual CadQuery geometry with the scoped NumPy/analytical beam recipe. No generic structural or fatigue capability is inferred.

Every modeled case records test verification and freeze before candidate submission, hard-requirement coverage, actual outcomes, final evidence completeness, search iterations, fresh repeated final evaluation, and runtime/cost provenance. Deliberately bad candidate detection, evaluator freeze rejection, unavailable capability rejection and final evidence completeness are executable assertions. Repetition tolerances are 1e-6 absolute or 1e-8 relative in each metric's stated unit. Independently verified suites can have different suite IDs because they contain distinct reference-evidence records; cross-driver comparisons require equal physical plan/evaluator/runtime/execution contracts and metric agreement. Existing strict-input route-parity tests also remain required.

Model cost is zero for fixtures; tokens are not fabricated. Local compute dollars are unknown without a price model. Reported elapsed solver time and allocated CPU × time are retained, with the latter labeled an upper bound rather than measured CPU consumption. Container setup, orchestration and developer time are not included in that solver-time figure.

The held-out memory comparison freezes a three-note reusable corpus **before** either task/arm: a useful qualitative stiffness lesson, a deliberately false stiffness/vibration claim and an incompatible impact-material lesson. Numeric task answers and candidate proposals remain outside reusable memory. A central retrieval allowlist applies to both drivers, including vector results; disabled retrieval returns nothing. Task-specific outcomes from one arm cannot leak into the other. All proposals are scripted identically across arms to isolate orchestration and retrieval; this experiment cannot measure autonomous use of lessons.

## Observed results and negative evidence

The recorded full native run completed six modeled cases per driver. All twelve had test-first ordering, complete declared coverage and complete final evidence. Repeated final metrics matched exactly; physical-contract and metric parity held between routes. Both detected the bad evaluator, regression geometry, unavailable fatigue and resource shortfall. Final designs passed in four cases per driver; both arms of the second held-out task still failed its 0.5 mm deflection constraint (0.564374 mm). A completed report therefore did not become a validated design.

The final structural bracket had nominal mass 22.9702 g, load displacement 0.0129491 mm and gauge stress 1.05184 MPa under its frozen static contract. This is evidence for that adapter/case, not fatigue, peak-notch strength or manufacturing certification. See [structural scope and reference tolerances](structural-simulation.md).

Both held-out tasks retrieved the useful note, the false note and the impact note. Precision@3 was 1/3; two suggestions were misleading or incompatible, and the impact note was explicitly flagged incompatible. Iteration and mass differences between memory arms were zero; acceptance was not lost. There is **no demonstrated memory-driven engineering performance improvement**. The same-metadata false lesson remained a hypothesis requiring agent judgment and independent tests.

Synthetic observation checks separately fit a 0.2 g offset. One synthetic hold-out residual improved from 0.2 g to approximately zero; another worsened from 0.2 g to 0.4 g. These numbers were deliberately constructed for software verification and are **not laboratory results** or evidence of real calibration benefit.

## Opt-in live-model protocol

A separately installed module supports a small, explicitly funded comparison on the fixed beam request. Use an ordinary managed workspace service with configured server-side credentials and pricing. Predeclare a reusable corpus with no held-out answers, then:

```bash
python -m davinci.product.live_methodology --workspace ./live-workspace \
  --output ./live-evidence --operation live-campaign-1 \
  --allow-paid-model-calls --budget-usd 10 --trials 2 \
  --memory-ids EXPERIENCE_ID_1 EXPERIENCE_ID_2
```

This is **not run by default or in CI**. Opt-in and a total budget in (0,25] USD are checked before connecting. The budget is split across both arms and 1–3 trials; each run has at most four candidates, bounded solver jobs/compute and a one-hour cancellation deadline. Trial order alternates, and model/runtime identities and every failed, uncertain, exhausted or successful outcome are retained. Resume an uncertain provider request only through the existing explicit resolution process; rerunning the protocol does not authorize duplicate spending.

A separate algebraic check compares final predictions and the predeclared physical inputs/limits. Changed loads, relaxed thresholds or missing final evidence fail protocol acceptance even if a run reports acceptance under its own suite. Analyze all trials, model spend, solver time, acceptance, mass and retrieval errors together; report failed and pending-input trials, not just successful examples. With two trials, differences are descriptive and too small for a robust causal or general engineering-improvement claim. No live-model evaluation was performed in this phase.

## Audit and known boundaries

[Capability matrix](capability-matrix.md) separates implemented interfaces from verified physics and unavailable evidence. Fast tests cover restart/cancellation, unknown provider requests, missing capability, linked evaluator correction, handoff/continuation, legacy viewing, export/import and scoped retrieval. Native checks and fresh-wheel runs are separate from those fixture tests. The implementation record gives the exact checks performed.

The supported analytical screen and optional linear-static solver cannot test nonlinear behavior, fatigue, contact or general dynamics. Hardware/resource estimates remain estimates; meshing, convergence and resource failures stay incomplete. Calibration authenticates neither the specimen nor the laboratory. Model-authored geometry and tests can be wrong; trusted references and coverage gates reduce risk within their stated scope and do not establish universal verification.
