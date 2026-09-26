# Local and live verification — 2026-09-26

Verified on the current Linux host: AMD Ryzen 7 7700X (8 cores / 16 threads), approximately 61 GiB RAM, Docker 29.6.1.

## Checks completed

- **19 API/ledger/provider/validation tests passed:** durable storage, atomic job claims, stale leases, stopped jobs, concurrent budget reservations, scoped memory, authentication/origin validation, concurrent run admission, portable export, image-budget estimation, cancellation without release rollback, import isolation, resumable validation IDs, external-error redaction, trigger duplicate-delivery behavior, and quarantine of missing/cross-run job sources.
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

## Trigger configuration and self-improvement

Both Database Triggers passed independent insertion probes with all workers
stopped. Correct jobs were observed for both candidate and evaluation records.
The linked service is `Cluster0`, and the two triggers must use distinct matching
candidate/evaluation handlers. Earlier probes exposed an incorrect service name
and the evaluation handler attached to the candidate trigger.

That handler mismatch caused `live2` to fail before evaluation after $0.16401028
of model/embedding usage. Its records remain archived. The worker now quarantines
jobs whose source document is missing or belongs to another run, without failing
the valid run. Two regression cases and the full replay integration test passed
after this fix. The successful first live run relied on reconciliation while
trigger configuration was being repaired; it was not used as trigger proof.

Because live1 had no geometric failures, explicit diagnostic reflection used
archived replay failures, clearly labelled as such. Astra generated tool
`tool-area-49a71c05c68127e0`, which passed independent tests and executed after an
engine restart. It generated release `release-705e594f50cb4728`, which passed
adaptation fixtures, React compilation/rendering, and real structural/aerodynamic
CAD canaries. A deliberately broken release was rejected without replacing it.

Astra visual inspection passed and archived its screenshots. A final screenshot
review caught an initial readiness check accepting the reference preview; both
inspection and acceptance now wait for evaluated CAD geometry explicitly. The
visual check was repeated on live3 and records the inspected geometry artifact.
Validation requires a newly created inspection, so an older record cannot mask
a failed retry. The live1 export
contained 60 entries; all 33 manifest hashes passed, with 24 evaluation-artifact
references downloaded directly from GridFS.

## Final acceptance

The final trigger-enabled run, `run-atlas-validation-20260926-live3`, completed
two rounds: four passing evaluations and two accepted assemblies. All four
candidates used the promoted Astra release, included the generated tool in their
context, invoked that tool, and retrieved historical memory. Its ZIP contained
49 entries, with all 22 artifact hashes verified and 12 evaluation-artifact
references downloaded directly from GridFS.

Final acceptance passed at **2026-09-26 17:58 UTC**. The API reports Atlas storage,
CAD availability, and live-model availability; both triggers are enabled. The
workbench rendered evaluated geometry without browser errors. No optimization
run is active, and no API budget reservation remains outstanding.

Total recorded model/embedding cost for this validation session, including the
failed diagnostic run, reflection, and visual inspection, is **$1.30446780** of
the approved **$25** limit. This uses the application's usage-based price ledger,
not a provider billing invoice. The earlier standalone credential probes are
outside this session. The fixed $10/$10/$5 allocations remain consumed as named
slots; rerunning a slot cannot create a fresh allowance.

The production stack remains available at **http://127.0.0.1:3215** with two
workers and `DAVINCI_USE_ATLAS_TRIGGERS=true`. Final UI evidence is stored at
`runtime/validation/final-workbench.png`. See
[live validation procedure](live-validation.md). Runtime reports are stored in
`runtime/validation/report.json` and Atlas `validations`.

FEA, viscous CFD, distributed workers, and whole-application UI redeployment
remain the documented post-hackathon phases. Existing engineering results are
analytic screening, not physical or flight validation.
