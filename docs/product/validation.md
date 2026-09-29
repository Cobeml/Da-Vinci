# MVP validation — 2026-09-29

## Automated checks

- 45 unit/API checks passed across the repository, including checkpoint recovery, budget enforcement, local memory isolation, runtime-version isolation, continuation, and request-origin validation.
- Real Docker baselines passed for sensor, gripper, stable VTOL, and the custom plate starter. The custom starter also rejected a physically failing thinner plate.
- Browser acceptance exercised object creation, actual CAD replay, interactive rendered geometry, downloads, continuation, reload, mobile layout, and invalid configuration handling.
- Both the standalone static UI and website production builds passed.
- A fresh Python 3.11 environment outside the checkout installed the wheel and validated a custom task without Node.js or host CadQuery.
- Atlas document and GridFS round-trips passed in a separate validation database. A new live Vector Search index was not provisioned for this check; vector retrieval remains optional with scoped fallback.

## Bounded live test

Two sensor runs completed through the new product engine, using one generated utility tested independently and invoked four times. The second run continued from the first run's best passing design.

| Stage | Measured STEP mass | Independent screening |
|---|---:|---|
| Initial baseline | 83.5354 g | Passed |
| First run's proposal | 76.7964 g | Passed |
| Continuation baseline | 76.7964 g | Passed |
| Continuation proposal | 70.0584 g | Passed |

The goal was a conservative mass reduction under unchanged geometry, stiffness, and stress checks. These are engineering screening results, not hardware validation or an ablation study.

Successful runs recorded $0.302600 of conservative token accounting. An earlier failed API-format attempt and diagnostic reservation remain archived, bringing total accounting to $1.314060 under the combined $10 cap. Accounting uses configured rates and is not a provider invoice.

The API integration was corrected to include the JSON output instruction in the input message. The viewport check was strengthened after camera fitting initially produced blank previews; it now checks actual rendered model pixels.

Detailed run evidence remains in `runtime/product-live-smoke/` on the development host. Credentials were consumed internally and were not displayed or copied into the package. Archived hackathon studies and beta results were not altered.

## Release limits

The package is built locally and is not published to PyPI. Linux was exercised directly; WSL2 installation is documented but was not tested on a Windows host. Public redistribution still requires review of the upstream solver and measured-data terms described in `THIRD_PARTY_NOTICES.md`. The local product is single-user and loopback-only.
