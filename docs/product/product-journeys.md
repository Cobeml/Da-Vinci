# External and built-in agent journeys

Both drivers use one localhost service, the same immutable suites and isolated CAD execution, and the same SQLite/local artifact storage (optional Atlas/GridFS). Credentials are server-side. Neither a completed execution, a reused lesson nor a met objective target alone establishes physical acceptance.

Install the wheel following [quickstart](quickstart.md). These commands run from outside the checkout with the installed `davinci` executable available. Linux/Python 3.11, Git and Docker are required. Node is only needed when building the UI/wheel from source.

## External coding agent: no model key or database

```bash
davinci init beam-external --driver external --template custom
cd beam-external
davinci setup --template custom
davinci doctor --driver external
davinci service ensure
davinci external instructions
davinci external schemas
python external/walkthrough.py
```

The last command is the packaged, agent-readable example implemented solely with public operations. It retrieves experience, authors the explicit beam plan, builds reference-only fixtures, verifies passing/failing behavior, freezes the suite, submits a failing 2 mm design and a revised 4 mm design, independently evaluates each, records unverified reflections, and exports the report and STEP files. It does not construct a generation or embedding provider.

Open `http://127.0.0.1:8741`, choose the object, and inspect both iterations, the frozen tests, actual outcomes, artifact manifests and final report. Copy the printed experiment ID into these commands:

```bash
davinci external status EXPERIMENT_ID
davinci external results EXPERIMENT_ID
davinci external report EXPERIMENT_ID --output final-report.json
davinci memory search 'cantilever failure' --experiment EXPERIMENT_ID
```

For a new request, **New object → External agent** opens a taskless draft. Give the coding agent the displayed workspace path and copyable instructions. It should author its own requirements/tests/source bundles using the public operations, not edit the database. The [external walkthrough](external-agents.md) documents every authoring and execution command.

## Built-in agent: description to report

In another directory and terminal:

```bash
davinci init beam-managed --driver managed
cd beam-managed
davinci setup --template sensor
```

Configure `OPENAI_API_KEY` in this workspace's `.env` or the service environment. Set the selected model, matching pricing identity/accounting rates, output limit and daily budget in `workspace.yaml`. Do this before starting the service; never put keys in YAML run descriptions, browser forms or candidate source. If the other workspace is still serving, use a different `port` in this workspace's settings.

```bash
davinci doctor --driver managed
davinci service ensure
davinci managed request --object beam --name 'Aluminium cantilever' \
  --operation-id beam-1 --budget-usd 10 --max-candidates 4 --search coordinate \
  --description 'Minimize mass of a rectangular prismatic aluminium cantilever: length 40 mm, width 20 mm, thickness 2 to 8 mm, clamped root, transverse tip force 100 N. Nominal E=70000 MPa and density=0.0027 g/mm3. Hard limits: stress <=100 MPa and tip deflection <=0.5 mm. Analytic small-deflection static screening only; no joints, fatigue or dynamic loads.'
```

Alternatively choose **New object → Built-in agent** in the installed UI. Enter the description, image, candidate limit and budget. No task directory is required. The agent authors and verifies tests before freezing the suite and generating CAD. If critical engineering information is missing, answer the displayed question. Ordinary stages continue automatically.

```bash
davinci managed status EXPERIMENT_ID
davinci managed answer EXPERIMENT_ID --operation-id answer-1 --file answers.json
davinci managed results EXPERIMENT_ID
davinci managed report EXPERIMENT_ID
```

The answer command is only needed for genuine pending questions; `answers.json` maps the displayed question IDs to answers. The UI exposes assumptions, coverage, fixed test inputs, numerical accuracy, uncertainty limits, unavailable capabilities, source/geometry/solver artifacts, retrieved experience and final evidence. Default optimization continues past a passing baseline. Optional objective attainment remains separate from hard acceptance.

Automatic new-test authoring currently supports the rectangular cantilever analytic-screen recipe. Unsupported physics/materials stop before candidate generation. A passing screen is not a claim of general FEA accuracy, fatigue life, manufacturing suitability or laboratory validation. Advanced YAML/custom-task templates remain available through the third choice in **New object**.

## Optional continuation or handoff

Neither route requires a handoff. To switch drivers at an idle frozen checkpoint, use the UI controls or:

```bash
davinci experiment handoff EXPERIMENT_ID --driver external --owner coding-agent \
  --operation-id handoff-1 --reason 'Continue design reasoning with my coding agent'
```

Use `--driver managed --owner user` to let the built-in agent adopt a verified suite with an inspectable builder. Generation credentials must be configured for live mode. The suite, tests, limits, current results and spending stay unchanged. Active/queued execution and stale owners/revisions are rejected atomically. Driver labels are not network authentication: the service remains localhost-only with host/origin protections.

To start a new run from a chosen candidate:

```bash
davinci experiment continue EXPERIMENT_ID --candidate CANDIDATE_ID \
  --driver external --owner coding-agent --operation-id continue-1 \
  --focus 'Improve mass while retaining every frozen requirement' --budget-usd 10
```

The command returns the new experiment ID. It has the same frozen suite and a submitted seed with identical source/parameters; no candidate scores are inherited. External users explicitly schedule evaluation, inspect it, reflect, then finalize or propose another candidate:

```bash
davinci external evaluate NEW_EXPERIMENT_ID --operation-id seed-evaluation
davinci external status NEW_EXPERIMENT_ID
davinci external wait NEW_EXPERIMENT_ID JOB_ID
davinci external results NEW_EXPERIMENT_ID
```

For a managed continuation, change `--driver managed --owner user`; the worker evaluates the seed and continues automatically. Requirements changes use a linked plan revision, not continuation or handoff. See [workspace ownership rules](workspace.md).

## What parity proves

Native checks run identical candidate source/parameters, candidate version, suite/evaluator/execution identity and pinned runtime through managed and keyless external routes. For the analytic beam recipe, they require identical statuses and units and metric agreement within **1e-6 absolute or 1e-8 relative**. Each route executes the physics; results are not copied or cached. This is parity for those inputs and that analytic screen, not proof of equivalence for all solvers or improved designs.

Default automated reasoning uses deterministic provider fixtures. Native tests use actual CadQuery/OCP and NumPy containers. A fresh-wheel test repeats both complete routes outside the checkout. Paid live-model smoke tests remain separately opt-in and budgeted; a credential's presence never enables them.
