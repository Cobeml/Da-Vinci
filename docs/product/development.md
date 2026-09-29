# Development and release

The product implementation lives in `davinci/product`. The standalone UI is `ui/`; the existing website is `web/`. Both import the product gallery component. Archived study scripts and beta tools are separate from the product execution path.

```bash
uv sync --extra studies
npm ci
npm run build:ui
uv run pytest tests/product -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py -q
npm run build
uv build --no-build-isolation
```

The static Next.js export is copied into package resources before wheel/sdist generation. Building the wheel is a contributor operation; running it requires no Node.js. Do not include workspace `.env`, `.davinci`, public demo assets, or runtime results in release artifacts.

The API is under `/api/v1`: tasks, validation, object list/detail, run creation/detail/stop/resume/YAML/events, candidate detail, and artifact access. POST bodies use JSON; run creation and validation receive `{"yaml": "..."}`. CLI and UI submit through this same path.

Run the product browser checks with `npm run test:product`. They start a temporary replay workspace and exercise real local geometry. Existing website tests remain under `tests/browser` and expect the website on port 3215.

Before release, install the wheel in a fresh environment outside the checkout, run all baseline adapters, run replay and continuation tests, inspect the package contents, and verify notices. CI builds wheel and sdist as downloadable artifacts; it does not publish to PyPI or deploy a public website.

Public release requires a final review of third-party solver and dataset redistribution terms, especially XFOIL and the UIUC propeller data. Project code is Apache-2.0; that does not relicense third-party dependencies or measurements.

Use Git commits for coherent changes. Never modify frozen archived evaluator files in place to reinterpret published results. Product adapter updates create new task hashes and new run baselines.
