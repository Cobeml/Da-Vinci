# Da Vinci: Recursive Improvement CAD Harness

Da Vinci runs CAD optimization from a Python package with a localhost web interface. Define an engineering task and quantitative constraints in YAML, watch the agent generate and evaluate designs, then continue from any buildable iteration with revised goals.

The object gallery shows interactive 3D models. Each object has its own run history, design iterations, metrics, checks, reflections, and STEP downloads.

## Run locally

The MVP supports Python 3.11 on Linux and Windows through WSL2, with Git and Docker. It is not yet published to PyPI. Clone the [repository](https://github.com/Cobeml/Da-Vinci):

```bash
git clone https://github.com/Cobeml/Da-Vinci.git
cd Da-Vinci
```

Follow the [source installation guide](docs/product/quickstart.md) to build and install the package (requires Node.js 22 and uv). Then, from your workspace parent directory:

```bash
davinci init my-project --template sensor
cd my-project
davinci setup --template sensor
davinci doctor
davinci serve
```

Set `OPENAI_API_KEY` in your environment or workspace `.env`. Edit `run.yaml`, then submit through the browser or another terminal:

```bash
davinci validate run.yaml
davinci run run.yaml
```

The UI opens at `http://127.0.0.1:8741`. SQLite and local files work without MongoDB. Node.js is required only to build the UI from source, not to run an installed wheel.

## Define a run

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
2. **Create and reuse tested tools:** generate a numeric utility, test it independently, and preserve it for compatible runs.
3. **Evaluate and revise:** independently evaluate exported geometry, retain every attempt, and rank passing designs under fixed checks.

**Continue from here** creates a linked run from a selected design. Goals, constraints, iteration count, and budget can change; earlier results remain intact. The installed application and evaluator are not rewritten by the agent.

## MongoDB Atlas

Atlas is optional. Documents preserve run state and evidence, GridFS stores CAD artifacts, and Vector Search retrieves relevant prior results. Local mode uses SQLite, local artifacts, and scoped structured/lexical memory. The product worker does not require Database Triggers. [Atlas setup](docs/product/atlas.md).

## Recorded results

The website's `/demo` is a read-only object gallery linking to the sensor mount, gripper, and VTOL studies. These are archived experiments, not claims about every future run.

| Study | Objective | Recorded improvement |
|---|---|---|
| Sensor mount | Reduce mount mass under fixed screening constraints | [83.54 → 30.33 g, 63.7% reduction](docs/sensor-gallery.md) |
| Parallel gripper | Reduce moving jaw mass while preserving stiffness and travel | [523.57 → 193.19 g, 63.1% reduction](docs/studies/gripper.md) |
| Survey VTOL | Increase estimated range with speed and payload protection | 68.33 → 85.14 km, +24.6% |

<details>
<summary>Evaluation scope and agent harness</summary>

The model proposes a CadQuery builder and parameters. Separate, resource-limited Docker containers build STEP and evaluate it against the task's fixed geometry/physics contract. Results, source snapshots, reflections, tested tools, runtime image digest, and request accounting are retained.

Sensor and gripper metrics use structural screening models. VTOL metrics use coupled aerodynamic and energy estimates. The historical VTOL campaign includes additional finalist checks; new product runs do not automatically reproduce those checks. These are engineering estimates, not flight-test, fatigue, manufacturing, or certification results. Failed designs remain visible and cannot become the best passing design.

Read the [architecture guide](docs/product/architecture.md) and task-specific study notes for assumptions. There is no ablation proving how much of each archived improvement is attributable to an individual self-improvement method.

</details>

## Documentation and contribution

[User guide](docs/product/README.md) · [YAML reference](docs/product/configuration.md) · [Continuing runs](docs/product/workspace.md) · [Custom tasks](docs/product/custom-tasks.md) · [Development](docs/product/development.md)

Project code is licensed under [Apache-2.0](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for separate dependency and data terms. Public package publishing is a separate release step.
