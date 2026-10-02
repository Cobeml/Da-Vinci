# Da Vinci: Recursive Improvement CAD Harness

Da Vinci is a Python package with a localhost web interface for iterative CAD engineering. Use an external coding agent or the built-in agent to define requirements, verify and freeze tests, create CAD, independently evaluate designs and preserve evidence. The gallery shows interactive models, iterations, actual outcomes and artifact downloads.

## Run locally

Python 3.11, Linux (or WSL2), Git and Docker are required. PyPI publication is pending. Build from source using Node.js 22 and uv:

```bash
git clone https://github.com/Cobeml/Da-Vinci.git
cd Da-Vinci
```

Follow the [source installation guide](docs/product/quickstart.md) to build the UI and install the wheel. Then choose a route:

**External coding agent — no Da Vinci model key or cloud database:**

```bash
davinci init my-project --driver external --template custom
cd my-project
davinci setup --template custom
davinci doctor --driver external
davinci service ensure
davinci external instructions
```

Your coding agent supplies reasoning through the public CLI/API. The [walkthrough](docs/product/external-agents.md) covers task authoring, failed candidates, revisions and final reports.

**Built-in agent — description to report:** initialize a separate workspace with `--driver managed`, run `davinci setup --template sensor`, configure model credentials and spending on the server, then run `davinci service ensure`. In the localhost UI choose **New object → Built-in agent**. Automatic test authoring currently supports rectangular cantilever screening; unsupported physics stops before modeling. See [complete user journeys](docs/product/product-journeys.md).

SQLite and local artifacts are the default. Embeddings are disabled by default and independent of generation credentials. The installed UI runs at the printed loopback URL, normally `http://127.0.0.1:8741`; Node.js is needed only when building it.

## Advanced YAML / legacy templates

```yaml
version: 1
object:
  slug: inspection-mount
  name: Inspection sensor mount
task:
  template: sensor
  description: Reduce material while preserving mounting interfaces and stiffness.
objective:
  metric: mass_g
  direction: minimize
  target: 70
constraints:
  - metric: deflection_mm
    operator: "<="
    value: 0.5
    unit: mm
run:
  iterations: 6
  budget_usd: 10
  mode: live
```

Start with the sensor, gripper, or VTOL template. Use `--template custom` for your own Python builder and independent evaluator. [Custom-task docs](docs/product/custom-tasks.md) include a prompt for adapting the project with a coding agent.

## Self-improvement

1. **Reflect and remember:** carry measured failures, successful parameters, and versioned lessons into later proposals.
2. **Create and reuse tested tools:** develop numeric or narrowly scoped CAD helpers, verify against independent references, and pin tested versions with promotion/rollback records.
3. **Evaluate and revise:** independently evaluate exported geometry, retain every attempt, and rank passing designs under fixed checks.

Continuation creates a linked experiment from a selected design without inheriting passing scores. The frozen suite stays fixed; changing requirements or correcting an evaluator needs a linked plan revision and renewed evidence. Driver handoff is explicit and exclusive. The installed application and evaluator are not rewritten in place.

## MongoDB Atlas for Scalable Model Improvement

Choose Atlas when configuring persistence. Documents preserve run state and evidence, GridFS stores CAD artifacts, and Vector Search retrieves relevant prior results. Local mode uses SQLite, local artifacts, and scoped structured/lexical memory. The product worker does not require Database Triggers. [Atlas setup](docs/product/atlas.md).

## Recorded results

The website's [/demo](https://www.dvcad.com/demo) leads with native structural and mechanism validation, followed by the historical model-driven sensor, gripper and VTOL studies. All are recorded evidence, not guarantees about future requests.

| Study | Objective | Recorded improvement |
|---|---|---|
| Structural bracket | Fixed 20 N linear-static test | Deflection 0.178 → 0.0129 mm; mass 18.30 → 22.97 g (scripted revision) |
| Vertical slider | Fixed 0.4 N motor and 30 mm lift | Moving mass 64.8 → 30.59 g; failed → passing motion (scripted revision) |
| Sensor mount | Reduce mount mass under fixed screening constraints | [83.54 → 30.33 g, 63.7% reduction](docs/sensor-gallery.md) |
| Parallel gripper | Reduce moving jaw mass while preserving stiffness and travel | [523.57 → 193.19 g, 63.1% reduction](docs/studies/gripper.md) |
| Survey VTOL | Increase estimated range with speed and payload protection | 68.33 → 85.14 km, +24.6% |

The newer cases use actual pinned native solvers with scripted external/deterministic managed reasoning. They establish scoped workflow and adapter evidence, not autonomous reasoning quality. The held-out memory benchmark has not demonstrated a design benefit. Measurement/calibration fixtures are synthetic; no laboratory measurements are claimed. See the [capability matrix](docs/product/capability-matrix.md).

<details>
<summary>Evaluation scope and agent harness</summary>

The model proposes a CadQuery builder and parameters. Separate, resource-limited Docker containers build STEP and evaluate it against the task's fixed geometry/physics contract. Results, source snapshots, reflections, tested tools, runtime image digest, and request accounting are retained.

Sensor and gripper metrics use structural screening models. VTOL metrics use coupled aerodynamic and energy estimates. The historical VTOL campaign includes additional finalist checks; new product runs do not automatically reproduce those checks. These are engineering estimates, not flight-test, fatigue, manufacturing, or certification results. Failed designs remain visible and cannot become the best passing design.

Read the [architecture guide](docs/product/architecture.md) and task-specific study notes for assumptions. There is no ablation proving how much of each archived improvement is attributable to an individual self-improvement method.

</details>

## Documentation and contribution

[User guide](docs/product/README.md) · [YAML reference](docs/product/configuration.md) · [Continuing runs](docs/product/workspace.md) · [Custom tasks](docs/product/custom-tasks.md) · [Development](docs/product/development.md)

Project code is licensed under [Apache-2.0](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for separate dependency and data terms. Public package publishing is a separate release step.
