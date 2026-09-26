# Atlas and Astra validation

Credentials stay in the ignored root `.env`. Do not print it or copy credentials
into commands, reports, screenshots, or browser variables. Setup and validation
commands report fixed error classifications instead of raw SDK exceptions.

## Provision and prove infrastructure

Stop the existing stack first. Keep the SQLite ledger and existing artifact
directory; switching to Atlas does not migrate or delete them.

```bash
.venv/bin/python -m scripts.atlas_setup
.venv/bin/python -m scripts.validate_atlas infrastructure
.venv/bin/python -m scripts.validate_atlas recovery
.venv/bin/python -m scripts.validate_atlas prepare
```

Setup waits up to ten minutes for the vector index. Repeated setup verifies
existing definitions; incompatible validators or vector settings require review
instead of silent replacement. Infrastructure verification uploads an artifact
and reads it from GridFS with an empty local cache.

In Atlas → Streaming Data → Triggers, create these Database Triggers:

| Name | Collection | Function to paste |
|---|---|---|
| `davinci_candidate_insert` | `candidates` | `runtime/validation/triggers/enqueue-candidate.js` |
| `davinci_evaluation_insert` | `evaluations` | `runtime/validation/triggers/enqueue-reflection.js` |

Each trigger must reference its own matching function. Do not bind both triggers
to the evaluation handler: a candidate ID is not an evaluation ID.

Select the configured cluster and database (default `da_vinci`). Use INSERT only,
enabled triggers, event ordering disabled, and preimages disabled. Retain the
full document. Prepared functions contain the configured database name directly;
no context value is necessary. Set `DAVINCI_ATLAS_SERVICE` in `.env` to the exact
linked service name shown in Atlas before running `prepare` (this deployment
uses `Cluster0`). The default template name is `mongodb-atlas`. Restarting a
trigger does not replace the function source: save the prepared function in
each dashboard trigger after changing this setting.

With the application workers still stopped:

```bash
.venv/bin/python -m scripts.validate_atlas triggers
```

This stage never enqueues jobs locally or invokes reconciliation. It gives each
attempt fresh diagnostic record IDs and waits two minutes for Atlas to create
both jobs. Diagnostic runs are terminal and hidden from the workbench. Recovery
is tested separately, including concurrent claims, stale leases, cancellation,
and a budget reservation refusal without making model calls.

Set `DAVINCI_USE_ATLAS_TRIGGERS=true` in `.env`, preserving credentials, and start
the production stack with `bash scripts/dev.sh --production` after a successful
`npm run build`. Uvicorn now uses `davinci.api:create_app --factory` so imports
do not initialize a database.

## Run bounded validation

The fixed session `atlas-validation-20260926` reserves named live slots of $10,
$10, and $5. Run IDs and budgets persist in Atlas. Reinvoking a slot resumes its
existing record; it does not create another spending allowance. All paid CAD,
embedding, reflection, and inspection requests use the same run budget ledger.
No new session or additional slot should be created to bypass the $25 limit.

With the two application workers running:

```bash
.venv/bin/python -m scripts.validate_atlas run --slot replay --rounds 4
.venv/bin/python -m scripts.validate_atlas monitor --slot replay
.venv/bin/python -m scripts.validate_atlas run --slot live1 --rounds 4
.venv/bin/python -m scripts.validate_atlas monitor --slot live1
.venv/bin/python -m scripts.validate_atlas vector --slot live1
.venv/bin/python -m scripts.validate_atlas reflection --slot live1
.venv/bin/python -m scripts.validate_atlas inspect --slot live1
.venv/bin/python -m scripts.validate_atlas export --slot live1
.venv/bin/python -m scripts.validate_atlas report
```

Only invoke explicit diagnostic reflection if the normal live loop has not
already demonstrated the required tool/release gates. It uses archived replay
failures with diagnostic provenance, generates a real Astra tool and patch,
tests them independently, and verifies reuse after restart. Run a subsequent
candidate to verify the activated release is applied, then run
`.venv/bin/python -m scripts.validate_atlas reuse --slot live3` (using the actual
subsequent slot). Use live2/live3 only for
targeted reruns or remaining checks; never reset existing run budgets.

The vector check directly queries Atlas with real embeddings and verifies
semantic scores plus scoped application retrieval. It does not accept lexical
fallback as success. Embedding backfills retain source evaluation provenance
and record which validation run paid for them.

Use `diagnose --slot live2` to inspect sanitized job errors and trigger probe
job kinds. The worker quarantines missing or cross-run source references as dead
jobs and emits `job_rejected`; it does not fail an otherwise valid design run.
A failed trigger test also reports the jobs it actually observed.

Reports and exports are in `runtime/validation/`; the session record is also
stored in Atlas `validations`. A monitor timeout stops its run. Budget exhaustion
or a failed gate is an incomplete check, never a reason to relax constraints.
Run `report` last to include spending from inspection and memory checks made
after CAD completion. Once all checks and the subsequent reuse run are complete,
run `acceptance` to verify service health, no active runs, no held reservations,
and actual browser rendering; it also captures the final workbench screenshot.
Archive actual evidence and remaining limitations in
`docs/verification.md`.
