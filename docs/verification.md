# Local and live verification — 2026-09-26

Verified on the current Linux host: AMD Ryzen 7 7700X (8 cores / 16 threads), approximately 61 GiB RAM, Docker 29.6.1.

## Checks completed

- **17 API/ledger/provider/validation tests passed:** durable storage, atomic job claims, stale leases, stopped jobs, concurrent budget reservations, scoped memory, authentication/origin validation, concurrent run admission, portable export, image-budget estimation, cancellation without release rollback, import isolation, resumable validation IDs, external-error redaction, and trigger duplicate-delivery behavior.
- **7 Docker/CAD integration tests passed:** measured mass and unit conversion, minimum thickness, hinge clearance, full reflection/tool-reuse loop, rejected patches, shared-assembly collision detection, unsupported geometry rejection, and validated release rollback. Some tests cover multiple scenarios.
- **4 Playwright tests passed against Atlas:** measured CAD rendering and navigation, mobile containment, starting/stopping runs, a full two-worker replay, and archived browser inspection screenshots.
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

## Atlas workflow verification

- Provisioning created validators and ordinary indexes. A second provisioning
  run passed without replacing existing definitions. `memory_vector` is READY
  and queryable with 1,536 dimensions.
- Atlas writes and GridFS upload/download passed. Remote reads used an empty
  local cache and checked SHA-256 digests.
- Atlas recovery checks passed: two concurrent claims produce one owner, expired
  leases can be reclaimed, stale owners cannot finish jobs, cancellation prevents
  execution, reconciliation repairs a missing job, and excess budget reservations
  are rejected without a model call.
- Named replay `run-atlas-validation-20260926-replay`: four rounds, eight
  evaluations, six passing candidates, three accepted assemblies, no model spend.
  Its portable ZIP contained 60 entries; all 33 manifest hashes were verified,
  and 24 evaluation-artifact references were independently downloaded from GridFS.
- Live run `run-atlas-validation-20260926-live1`: four rounds, eight passing
  candidates, four accepted assemblies, no job errors. CAD generation and
  embeddings consumed $0.63736974 before additional diagnostic checks.
- Direct `$vectorSearch` returned both archived failures and successes with
  similarity scores. Application retrieval returned the correct subsystem,
  specification, and evaluator cohort with semantic scores. Lexical fallback
  was not counted as a vector-search pass.

## Validation still in progress

The first independent trigger probe timed out with workers stopped; neither
trigger created its job. Trigger configuration is being diagnosed separately.
The live CAD run used the existing reconciliation path and does not establish
successful trigger delivery.

Astra-generated diagnostic tool/release validation, visual inspection, final
live export, and a subsequent run using the generated release remain pending.
The validation session has fixed $10/$10/$5 live allocations, totalling at most
$25; run IDs and spending persist across command restarts. See
[live validation procedure](live-validation.md). Runtime reports are stored in
`runtime/validation/report.json` and Atlas `validations`.

FEA, viscous CFD, distributed workers, and whole-application UI redeployment
remain the documented post-hackathon phases. Existing engineering results are
analytic screening, not physical or flight validation.
