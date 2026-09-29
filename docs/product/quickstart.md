# Install and run

Supported MVP environment: Python 3.11, Linux, Git, and Docker Engine. Windows users run the package inside WSL2 with Docker Desktop's WSL integration enabled. Native Windows and macOS have not been validated.

## Install this release

The package is not yet published to PyPI. Build a wheel from this checkout (Node 22 is needed only by contributors):

```bash
npm ci
npm run build:ui
uv sync --extra studies
uv build --no-build-isolation
```

Install the resulting wheel into a Python 3.11 virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install /path/to/da_vinci_harness-0.2.0-py3-none-any.whl
```

Once a release is published, installation will be `pip install da-vinci-harness`. Users of a wheel do not need Node.js, a repository checkout, or CadQuery installed on the host.

## Create a workspace

```bash
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

Open the printed localhost URL (default `http://127.0.0.1:8741`). Choose **New object** and load `run.yaml`, or submit it from another terminal in the same workspace:

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
