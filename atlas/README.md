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

## Connection checks and Tailscale

Run `.venv/bin/python -m scripts.check_connections --public-ip` before provisioning.
The command loads `.env` directly, prioritizes it over existing shell values,
checks OpenAI model access and MongoDB ping/database read access, and prints only
fixed diagnostic labels. It does not print credentials, connection strings, or
raw provider errors, and does not write to the database. Add `--inference` to
verify a small billable Astra Responses request as well. Exit code 1 means at
least one check failed. Neither check proves database write permissions or that
Atlas indexes/triggers have been provisioned.

For a direct connection from the hackathon workstation, add its **public egress
IPv4 address with `/32`** in Atlas **Security → Network Access → IP Access List →
Add IP Address**. A temporary entry can cover the event. Wait for the entry to
become Active, then rerun the check. If you open Atlas from another device,
“Add Current IP Address” may select that device's egress instead of the worker's.
The printed HTTPS egress IP is useful for direct connections; a proxy or
destination-specific route can make database egress differ.

A Tailscale `100.x` address by itself does not allow access to the public Atlas
endpoint. The [Tailscale Atlas guide](https://tailscale.com/docs/solutions/create-a-secure-connection-to-mongodb-atlas)
configures an **app connector** and allowlists that connector's **public egress
IP**. This is optional for a workstation connecting directly. If using an exit
node or app connector, allowlist its public egress address instead. Keep the
Atlas-provided hostname in `MONGODB_URI`; do not replace it with the workstation's
Tailscale IP. See [Atlas IP access lists](https://www.mongodb.com/docs/atlas/security/ip-access-list/).

DNS resolution and an open TCP port alone do not establish an authenticated
database connection. A selection timeout can still indicate an Atlas access-list
issue, firewall, or unavailable cluster. An authentication rejection means the
network connection succeeded but the database credentials need correction.
Restart the API and workers after updating `.env` so they pick up the new values.
