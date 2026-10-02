# Website and documentation update — 2026-10-02

The public `web/` site now presents the current lifecycle and two drivers; the installed product remains `ui/`. The landing identity and sensor-on-drone visual are preserved. `/demo` leads with the bracket and slider, then the historical sensor/gripper/VTOL studies. New `/structural` and `/mechanism` pages show native simulation results, failed/invalid candidates, a sampled recorded slider trajectory, final checks and downloadable evidence. Scripted/deterministic reasoning is visibly distinguished from historical model-driven proposals. The beta geometry tools remain unadvertised.

## Data and compatibility

`python3 scripts/export_recorded_demos.py` reads only the explicitly selected local archives using SQLite read-only connections. It verifies content hashes and bounded sizes, rejects symlinks and unsafe names, and copies allowlisted CAD, bindings, convergence, uncertainty and trajectory files. Public reports retain source/candidate/suite/result/runtime identities and quantitative uncertainty. Configuration, logs and workspace databases are not published. Builds consume the committed bundle and need no runtime archives, model key, cloud database or solver. The public bundle schema is version 1; it is a presentation export, not a new engine or importable acceptance record. The new bundle is approximately 1.2 MB.

Original archives, frozen suites and study measurements are unchanged. Archived v1 results retain their historical screening limits. The bracket's stiffness improvement costs mass; the slider's mass reduction has no structural-strength implication. Neither case is autonomous reasoning evidence. The memory benchmark's absence of demonstrated engineering benefit and the synthetic nature of measurement/calibration fixtures remain explicit.

`docs/product/navigation.json` controls public and installed documentation navigation. A Markdown navigation block also keeps the repository user guide readable on GitHub. Shared rendering preserves document anchors, README links and local JSON evidence URLs. The architecture uses accessible HTML, requiring no external diagram service. Quickstart and root README now lead with both routes; advanced YAML remains supported. The website's old `/harness` is labeled historical. Installed experiment views link to capability, memory and tool-learning guides. No database or configuration migration is required.

The three existing research citations were checked against their arXiv abstracts on 2026-10-02: [consistency guidelines](https://arxiv.org/abs/2609.08832), [SkillAlchemy](https://arxiv.org/abs/2608.23417), and [AIDE²](https://arxiv.org/abs/2609.26457). Their reported figures match the site's copy; they remain in a disclosure and are not presented as CAD-harness validation.

## Reproduction and checks

```bash
# Optional, only on the host with the preserved archives; never required for build:
python3 scripts/export_recorded_demos.py

node scripts/check_product_docs.mjs
npm run typecheck
npm run build
npm run build:ui
uv run pytest -m 'not integration' -q
npm run test:product
npm run test:site

# In another terminal, serve a fresh production build (restart after building):
npm exec -- next start web --hostname 127.0.0.1 --port 3225
DAVINCI_SITE_URL=http://127.0.0.1:3225 node_modules/.bin/playwright test \
  tests/browser/landing.spec.ts tests/browser/product-demo.spec.ts \
  tests/browser/recorded-evidence.spec.ts tests/browser/sensor-gallery.spec.ts \
  tests/browser/gripper-gallery.spec.ts tests/browser/vtol-gallery.spec.ts \
  tests/browser/surface-gallery.spec.ts

uv build --no-build-isolation
uv venv /tmp/davinci-website-wheel --python 3.11
uv pip install --python /tmp/davinci-website-wheel/bin/python dist/da_vinci_harness-0.2.0-py3-none-any.whl
cd /tmp
/tmp/davinci-website-wheel/bin/python /path/to/Da-Vinci/scripts/check_installed_docs.py
```

Executed: website typecheck and production builds; installed UI build; 185 existing fast tests plus both new public-evidence integrity tests; all 13 website browser checks; all five product browser scenarios, including deterministic managed/keyless external real CAD, clarification, missing capability, continuation/handoff and legacy replay. A fresh wheel outside the checkout served 32 guide routes and three evidence JSON downloads with no model or solver calls. Desktop/mobile screenshots are under `runtime/product-screenshots/`.

Initial browser attempts exposed a stale production server's cached route list and conflicting Playwright trace directories. Fresh-server testing and separate `test-results/website` / `test-results/product` paths resolved them. A real new-page mobile grid overflow was corrected; missing-GLB fallback and artifact checksum downloads now have regressions. Restricted sandbox child-process/TestClient checks were rerun with the required execution permission. Existing FastAPI/Starlette deprecation warnings remain.

No new structural/MuJoCo solver study, private Atlas check, laboratory measurement or paid live-model trial was run for this presentation update. Existing native evidence was copied and checked, not regenerated. Publication does not expand the validated physics scope.
