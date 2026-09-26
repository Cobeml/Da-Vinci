# Atlas setup

1. Create an Atlas deployment, database user, and IP access entry for the worker host.
2. Put its connection string in the server `.env` as `MONGODB_URI`. Do not put credentials in frontend variables.
3. Run `.venv/bin/python -m scripts.atlas_setup`. This creates validators, ordinary indexes, and the `memory_vector` search index.
4. In Atlas **Triggers**, create a Database Trigger for **INSERT** on `candidates`. Use the source in `enqueue-candidate.js` as its function. Enable full document delivery; ordering is not required.
5. Create a second INSERT-only trigger on `evaluations`, using `enqueue-reflection.js`.
6. Set the function context value `DAVINCI_DATABASE` to the same value as `MONGODB_DATABASE` (default `da_vinci`). The linked service is named `mongodb-atlas`; change that literal if your Atlas service uses another name.
7. Set `DAVINCI_USE_ATLAS_TRIGGERS=true`, add `OPENAI_API_KEY`, and restart the API and workers.
8. Start an Astra live run. Verify the candidate insert creates exactly one job, and evaluation insertion creates a reflection job. The worker's 15-second reconciler also repairs missing jobs.

Jobs use the same deterministic ID in Python and JavaScript, so at-least-once trigger delivery and reconciliation are idempotent. Trigger functions do not run CAD or call the model.

The local SQLite backend supports durable replay and lexical/structured retrieval. Atlas mode uses PyMongo, GridFS, and `$vectorSearch`; it does not use retired App Services Data API/HTTPS endpoints. Local records are not silently migrated into Atlas. Export a replay bundle before changing backends if you want to preserve a portable copy.

Timestamps in application documents are UTC ISO-8601 strings, consistently sortable in both storage backends. GridFS uses its native metadata dates. Evidence is append-only through the application repository; this is an application invariant, not a tamper-proof database claim.
