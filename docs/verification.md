# Local verification — 2026-09-26

Verified on the current Linux host: AMD Ryzen 7 7700X (8 cores / 16 threads), approximately 61 GiB RAM, Docker 29.6.1.

## Checks completed

- **13 API/ledger/provider tests passed:** durable storage, atomic job claims, stale leases, stopped jobs, concurrent budget reservations, scoped memory, authentication/origin validation, concurrent run admission, portable export, image-budget estimation, and cancellation without release rollback.
- **7 Docker/CAD integration tests passed:** measured mass and unit conversion, minimum thickness, hinge clearance, full reflection/tool-reuse loop, rejected patches, shared-assembly collision detection, unsupported geometry rejection, and validated release rollback. Some tests cover multiple scenarios.
- **4 Playwright tests passed:** measured CAD rendering and navigation, mobile containment, starting/stopping runs, a full two-worker replay, and archived browser inspection screenshots.
- Next.js production build and TypeScript validation passed.
- Python lint and Git whitespace checks passed.

The browser tests ran against the actual local API/workers and actual CadQuery artifacts. Fresh-ledger integration tests exercised the deliberately failing baseline and automatic release promotion. Those tests used replay without paid inference.

## Live connection verification

After credentials were configured, GPT-6 Astra model access and a small Responses
API inference request passed. MongoDB Atlas ping and database collection-list
access also passed after the workstation's public egress IPv4 address was added
to the project IP access list. Database routes did not use Tailscale; allowlisting
the workstation's Tailscale address alone was insufficient.

`.venv/bin/python -m scripts.check_connections --inference --public-ip` exited 0
with both services passing. Credentials were loaded directly by the SDK setup;
their values and raw error messages were not displayed. The check does not write
to Atlas or verify write permissions. Synthetic-secret redaction checks and
Python lint passed for the reusable checker.

## Compute benchmark

Ten alternating mount/wing candidates were built and evaluated at each concurrency level. Each job used a 2-CPU, 4-GiB container limit; geometry building and independent evaluation ran in separate containers.

| Workers | Ten-candidate elapsed time | Maximum evaluator RSS |
|---|---:|---:|
| 1 | 26.542 seconds | 482.0 MiB |
| 2 | 14.771 seconds | 481.7 MiB |

These measurements cover the bundled screening fixtures, not arbitrary CAD, meshing, CFD, or model latency. RSS is the evaluator process peak, not total host or container memory. Detailed samples are in [benchmark.json](benchmark.json).

## Remaining external validation

Atlas trigger delivery, GridFS writes on Atlas, Atlas Vector Search, and the full
Astra-driven CAD/reflection loop remain **not live-validated**. Follow
[Atlas setup](../atlas/README.md), restart the stack to load updated credentials,
then run the demonstration in Astra live mode.

The local workflow intentionally uses labelled deterministic replay and durable SQLite storage. FEA, viscous CFD, distributed workers, and whole-application UI redeployment remain the documented post-hackathon phases.
