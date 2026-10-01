# Development and release

The product implementation lives in `davinci/product`. The standalone UI is `ui/`; the existing website is `web/`. Both import the product gallery component. Archived study scripts and beta tools are separate from the product execution path.

```bash
uv sync --extra studies
npm ci
npm run build:ui
uv run pytest -m 'not integration' -q
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_cad.py -q
npm run build
uv build --no-build-isolation
```

The static Next.js export is copied into package resources before wheel/sdist generation. Building the wheel is a contributor operation; running it requires no Node.js. Do not include workspace `.env`, `.davinci`, public demo assets, or runtime results in release artifacts.

Pytest explicitly adds the checkout root to its import path so archived study tests can import `scripts.*` with either `pytest` or `python -m pytest`. These scripts are not part of the installed product. The separate fresh-environment wheel check runs outside the checkout to verify installed imports.

The API is under `/api/v1`: tasks, validation, object list/detail, run creation/detail/stop/resume/YAML/events, candidate detail, and artifact access. POST bodies use JSON; run creation and validation receive `{"yaml": "..."}`. CLI and UI submit through this same path.

Run the product browser checks with `npm run test:product`. They start a temporary replay workspace and exercise real local geometry. Existing website tests remain under `tests/browser` and expect the website on port 3215.

Before release, install the wheel in a fresh environment outside the checkout, run all baseline adapters, run replay and continuation tests, inspect the package contents, and verify notices. CI builds wheel and sdist as downloadable artifacts; it does not publish to PyPI or deploy a public website.

Public release requires a final review of third-party solver and dataset redistribution terms, especially XFOIL and the UIUC propeller data. Project code is Apache-2.0; that does not relicense third-party dependencies or measurements.

Use Git commits for coherent changes. Never modify frozen archived evaluator files in place to reinterpret published results. Product adapter updates create new task hashes and new run baselines.

## First PyPI release

The existing `product.yml` workflow tests and builds downloadable artifacts; it does not publish them. A missing PyPI release cannot cause a checkout test to fail to import `scripts`.

1. Get both CI jobs passing for the exact release commit. Complete the redistribution review described in `THIRD_PARTY_NOTICES.md`, including the bundled UIUC measurements and solver notices.
2. Choose an unused release version in `pyproject.toml` and update `uv.lock` if the version changes. Build the UI, wheel, and source distribution with the commands above. Run `uvx twine check dist/*`, inspect the archive contents, and install the wheel in a clean Python 3.11 environment outside the checkout. Exercise the localhost UI, packaged docs, and a replay CAD run. Check that the source distribution can rebuild a wheel with the bundled UI.
3. Create PyPI and TestPyPI accounts and configure two-factor authentication. Configure a pending Trusted Publisher for package `da-vinci-harness`, GitHub owner `Cobeml`, repository `Da-Vinci`, proposed workflow filename `release.yml`, and environment `pypi` (or `testpypi` for TestPyPI). A pending publisher does not reserve the package name. See [creating a project with Trusted Publishing](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).
4. Add `.github/workflows/release.yml` with a release or manual trigger, build/test gates, and separate publishing jobs. Configure matching GitHub environments. Give only the publishing jobs `id-token: write`; use `pypa/gh-action-pypi-publish@release/v1` to upload the tested artifacts. No long-lived PyPI API key is needed. See [the PyPI publishing setup](https://docs.pypi.org/trusted-publishers/using-a-publisher/).
5. Publish to TestPyPI first using `repository-url: https://test.pypi.org/legacy/`. Install that exact test artifact in a fresh environment, obtain its dependencies from normal PyPI, and repeat the installed-package smoke check. Then publish the same tested distributions to PyPI. See [packaging and TestPyPI verification](https://packaging.python.org/en/latest/tutorials/packaging-projects/).
6. Verify `pip install da-vinci-harness==<version>` from PyPI and the `davinci` command, then update the installation docs and README with the published version.

The publishing workflow and account setup above are future release steps; they are not enabled by the current CI workflow.

## Lifecycle foundation

See [the public lifecycle contracts](lifecycle.md) and [the implementation record](implementation-lifecycle.md) before changing lifecycle or compatibility behavior. The new v2 integration is included in `tests/product/test_cad.py`; the default non-integration suite includes deterministic external and managed driver fixtures. Do not run paid models or private databases merely because credentials exist.
