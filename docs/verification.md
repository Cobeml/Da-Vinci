# Local verification — 2026-09-26

Verified on the current Linux host: AMD Ryzen 7 7700X (8 cores / 16 threads), approximately 61 GiB RAM, Docker 29.6.1.

## Checks completed

- **13 API/ledger/provider tests passed:** durable storage, atomic job claims, stale leases, stopped jobs, concurrent budget reservations, scoped memory, authentication/origin validation, concurrent run admission, portable export, image-budget estimation, and cancellation without release rollback.
- **7 Docker/CAD integration tests passed:** measured mass and unit conversion, minimum thickness, hinge clearance, full reflection/tool-reuse loop, rejected patches, shared-assembly collision detection, unsupported geometry rejection, and validated release rollback. Some tests cover multiple scenarios.
- **4 Playwright tests passed:** measured CAD rendering and navigation, mobile containment, starting/stopping runs, a full two-worker replay, and archived browser inspection screenshots.
- Next.js production build and TypeScript validation passed.
- Python lint and Git whitespace checks passed.

The browser tests ran against the actual local API/workers and actual CadQuery artifacts. Fresh-ledger integration tests exercised the deliberately failing baseline and automatic release promotion. No paid inference calls were made.

## Compute benchmark

Ten alternating mount/wing candidates were built and evaluated at each concurrency level. Each job used a 2-CPU, 4-GiB container limit; geometry building and independent evaluation ran in separate containers.

| Workers | Ten-candidate elapsed time | Maximum evaluator RSS |
|---|---:|---:|
| 1 | 26.542 seconds | 482.0 MiB |
| 2 | 14.771 seconds | 481.7 MiB |

These measurements cover the bundled screening fixtures, not arbitrary CAD, meshing, CFD, or model latency. RSS is the evaluator process peak, not total host or container memory. Detailed samples are in [benchmark.json](benchmark.json).

## Remaining external validation

The user has not yet configured `OPENAI_API_KEY` or `MONGODB_URI`. Therefore Astra inference, Atlas trigger delivery, GridFS on Atlas, and Atlas Vector Search are implemented but **not live-validated**. Follow [Atlas setup](../atlas/README.md) when credentials are available, then run the same demonstration in Astra live mode.

The local workflow intentionally uses labelled deterministic replay and durable SQLite storage. FEA, viscous CFD, distributed workers, and whole-application UI redeployment remain the documented post-hackathon phases.
