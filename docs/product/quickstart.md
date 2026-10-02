# Install and run

Supported MVP environment: Python 3.11, Linux, Git, and Docker Engine. Windows users run the package inside WSL2 with Docker Desktop's WSL integration enabled. Native Windows and macOS have not been validated.

## Clone and install

The package is not yet published to PyPI. Install from the [GitHub repository](https://github.com/Cobeml/Da-Vinci). In addition to the prerequisites above, building from source requires Node.js 22 (with npm) and uv. Node.js is only needed to build the web interface; it is not needed to run the installed package.

Clone the repository and enter its directory:

```bash
git clone https://github.com/Cobeml/Da-Vinci.git
cd Da-Vinci
```

Build the web interface and Python wheel:

```bash
npm ci
npm run build:ui
uv sync --extra studies
uv build --no-build-isolation
```

From the same directory, install the resulting wheel into a separate Python 3.11 virtual environment. Keep this environment activated for the remaining commands:

```bash
python3.11 -m venv .venv-client
source .venv-client/bin/activate
python -m pip install dist/da_vinci_harness-0.2.0-py3-none-any.whl
```

The installed wheel includes the localhost web interface. CAD generation runs in Docker; no separate host CadQuery installation is required to use the package.

## External agent: no model key

Create the workspace alongside the repository. Your coding agent supplies reasoning; Da Vinci executes the frozen tests locally.

```bash
cd ..
davinci init my-project --driver external --template custom
cd my-project
davinci setup --template custom
davinci doctor --driver external
davinci service ensure
davinci external instructions
```

Open the printed localhost URL (default `http://127.0.0.1:8741`). **New object → External agent** displays connection commands. Give these and the instructions to your coding agent. The [complete external journey](product-journeys.md#external-coding-agent-no-model-key-or-database) includes a packaged failed-then-revised real CAD example. No embedding service is required.

## Built-in agent: description to report

In a separate workspace:

```bash
davinci init my-managed-project --driver managed
cd my-managed-project
davinci setup --template sensor
```

Configure `OPENAI_API_KEY` in the service environment or workspace `.env`, and select model/pricing and spending limits in `workspace.yaml`. Never enter keys into browser forms, task descriptions or candidate source. Initialization creates a `.gitignore`; do not commit `.env`.

```bash
davinci doctor --driver managed
davinci service ensure
```

Choose **New object → Built-in agent**, enter an engineering description and budget, then answer any genuine clarification questions. Requirements and verified tests precede new design generation. See the [complete managed example](product-journeys.md#built-in-agent-description-to-report).

Automatic test authoring currently supports the rectangular cantilever analytic-screen recipe. Gmsh/CalculiX and MuJoCo examples demonstrate authored suites through both drivers, using scripted/deterministic reasoning. They do not establish arbitrary natural-language structural or mechanism authoring.

## Advanced YAML and optional solvers

**New object → Advanced YAML / custom task** retains the existing `run.yaml` route. See [configuration](configuration.md) and [custom tasks](custom-tasks.md). Setting a legacy run's `mode: replay` uses deterministic proposals with real CAD execution; replay is distinct from the external driver.

`setup` builds the selected Docker image and needs internet on first installation. Execution runs without network access. Install optional physics explicitly:

```bash
davinci setup --template structural
davinci setup --template mujoco
```

Read the [structural scope](structural-simulation.md) or [mechanism scope](mechanism-simulation.md) before using those adapters. No optional solver is installed merely by opening the website. Local SQLite/artifacts are the default; [Atlas](atlas.md) is configured separately.

Closing the browser does not stop a run. Saved evidence remains under `.davinci`; after a service interruption, restart it and explicitly resume the experiment. [Workspace instructions](workspace.md) cover cancellation, continuation and exclusive driver handoff.

## Troubleshooting

- **CAD image unavailable:** start Docker, then run `davinci setup --template sensor` (or `vtol`).
- **Permission denied on Docker:** configure Docker access for your user; on WSL2, enable the distribution in Docker Desktop.
- **Port occupied:** set `port` in `workspace.yaml`, then restart `serve`.
- **UI unavailable:** source developers must run `npm run build:ui` before building the wheel.
- **Budget exhausted:** create a linked run with a new budget; existing results remain available.
- **Uncertain API request:** an interrupted request may have incurred cost. It is not retried automatically. Continue from a saved iteration in a new run. If there is no saved design, start a new run from the template.
- **Atlas unavailable:** configured Atlas failures do not silently switch databases. Restore connectivity or create a separate local workspace.

The product server binds only to loopback. Remote multi-user hosting and Tailscale access to this server are outside the MVP. The existing website demo remains available through its separate Tailscale listener.

## Start from a description

For supported automatically verified requests without a pre-authored task directory, use [managed requests](managed-requests.md): `davinci managed request --help`. The existing YAML and gallery workflow remains available.


## Two complete v2 journeys

See [both user journeys and handoff commands](product-journeys.md) for exact installed-package commands. In the browser, **Built-in agent** begins with a description and **External agent** displays copyable connection instructions. Both appear in the same gallery; native physics and provider-fixture checks are reported separately.
