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

## External coding agents

For a keyless workflow driven by your coding agent, use `davinci init my-project --driver external --template custom`, then `davinci --workspace my-project service ensure`. See [the external-agent walkthrough](external-agents.md) for task authoring, reference verification, queued CAD evaluation and report export. The managed workflow below remains available.

## Create a workspace

Create the workspace alongside the repository so its run data stays separate from the source checkout:

```bash
cd ..
davinci init my-project --template sensor
cd my-project
davinci setup --template sensor
davinci doctor
```

`setup` builds the isolated CAD image. It requires internet access on the first build; later CAD execution has no network access. The VTOL image also installs its aerodynamic solvers and takes longer to build.

Set `OPENAI_API_KEY` in your shell or workspace `.env`. No MongoDB connection is required. Avoid committing `.env`; initialization creates a `.gitignore`.

```bash
davinci validate run.yaml
davinci serve
```

Open the printed localhost URL (default `http://127.0.0.1:8741`). Choose **New object → Advanced YAML / custom task** and load `run.yaml`, or submit it from another terminal in the same workspace:

```bash
davinci run run.yaml
```

The terminal running `serve` must stay open. Closing the browser does not stop a run. If the server exits, saved evidence remains under `.davinci`; restart it and explicitly resume the interrupted run.

For a no-API-cost trial, set `run.mode: replay`. This uses deterministic proposals and reflections, while still building real geometry and running the evaluator in Docker. It is labeled replay throughout the interface.

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
