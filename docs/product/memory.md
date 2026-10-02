# Engineering experience and exact evidence

[Tested construction helpers](tool-learning.md) add `tool_reference` experiences with source/contract artifacts, dependency hashes, version links, independent check outcomes and promotion/rollback decisions. Retrieval does not activate a tool: use the current scoped registry and compatible run pin. Imported claims never register executable tools or transfer passing scores.

Both reasoning drivers use the same persistent memory service. The managed loop receives cross-object experience through `Engine.memory`; lifecycle reasoning uses the same search. External agents use `davinci memory` and `/api/v2/memory`. Simulation operations, memory search and indexing never instantiate the generation provider. SQLite/local artifacts work without keys, a cloud database or an embedding service.

## Two separate operations

**Experience search** retrieves lessons, observations, test recipes, modeling procedures and tested-tool references across objects in the active workspace/project. Applicability checks compare domain, phenomena, material models/material names, manufacturing processes, load regimes and declared numerical ranges. Quantity ranges are converted dimensionally before comparison. Conflicts are flagged `incompatible`; missing information yields `needs_review`. `compatible_metadata` means only that declared metadata agrees, never that physics has been validated for the new task. Set `include_incompatible: false` / `--reject-incompatible` to exclude conflicting records.

**Exact evidence lookup** requires the complete `ExactInputs` contract: exported geometry SHA-256, builder-source SHA-256, frozen suite/evaluator/runtime/harness identities, fixed physical-input hash, numerical-setting hash, parameter hash and observed solver/runtime hash. Changing any field prevents a match. Matching artifacts are verified again. Imported records and records with missing/corrupted evidence cannot supply exact local evidence. These are conservative byte identities, not geometric-equivalence guesses.

Result caching is **disabled**. Even an exact lookup returns `cache_enabled: false` and `reusable_for_acceptance: false`: this release cannot establish every arbitrary evaluator's determinism, environmental inputs and numerical equivalence. A candidate must run its own frozen suite. Reading a prior passing score does not create a current passing score or bypass lifecycle checks.

## Experience contract

`Experience` version 1 is discoverable in the installed `external/schemas.json` and `davinci external schemas`. It records:

- Source run, candidate, result, tests and tested tools; request and requirements; attempted change and measured outcomes.
- Domain, failure modes, material/process/load assumptions, quantitative applicability ranges, material/load inputs and test recipes.
- Claim, confidence basis, source support, local evidence status, artifact checksums and runtime/suite provenance.
- Origin, import history, supersession, revision and workspace/project access scope. `transfers_acceptance` is always false.

The harness projects committed outcomes into observation records, including physical failures and incomplete diagnostic evidence. A complete simulation observation may be `simulation_supported`; an incomplete record remains a hypothesis. It describes what the test measured at its stated fidelity, not a proven generalized design lesson.

Agent-written notes and reflections remain `hypothesis`, even when they link to a passing result. External clients cannot post support levels, trusted scores or acceptance decisions. Notes may cite existing tests or tools whose checks passed in the source run. Tested tool references retain check/commit provenance; they are not automatically executed or assumed valid in another task.

The schema distinguishes `hypothesis`, `simulation_supported` and `measurement_supported`. There is no trusted hardware-measurement ingestion route in this release. Imported claims may retain a measurement-supported source label, but always have `local_evidence_status: imported_unverified`. Imports do not authenticate another author's claim.

Supersession points an old record at a replacement and preserves the original text, measurements and reason. Superseded records are excluded by default; `--include-superseded` exposes misleading and corrected history. Revisions use compare-and-set; conflicting updates fail. Do not overwrite an old lesson to make the archive look successful.

## Scope and indexed retrieval

`workspace.yaml` selects one active `project_id` (default `default`). A persistent identifier in `.davinci/memory-workspace-id` identifies its memory namespace and moves with a workspace backup. Unrelated workspaces receive different identifiers. Both workspace and project filters are mandatory for search, inspection, exact lookup, export, supersession and source references. Choosing another project does not silently share existing lessons. Importing an explicitly exported bundle is the cross-project/workspace transfer operation. The `access_scope` label does not override these mandatory filters; there is no public/global sharing option or multi-user authorization service.

New records live in `experiences_v1`; idempotent import receipts use `memory_operations_v1`. SQLite uses expression indexes on scope/exact identity and a transactional FTS5 projection. Atlas uses scoped metadata/text indexes and optionally Vector Search. Filtering and limits run in the database before JSON decoding; these collections do not use `Store.list`'s legacy full-collection filtering path.

Search fuses metadata applicability, lexical overlap, optional vector similarity and evidence quality. Responses retain index lexical scores and `semantic_score`; vector ordering information is not discarded by a final lexical-only sort. Quality is a ranking heuristic, not a probability of correctness. Imported, hypothetical, superseded or incomplete evidence gets lower weight. Search reports `evidence_rechecked: false`; inspection and exact lookup verify artifact bytes.

The candidate window contains up to 200 indexed lexical/metadata hits plus up to 100 Atlas vector hits (response upper bound 400). Search paginates within that bounded window with a scoped query cursor and a creation-time cutoff. It is not exhaustive semantic recall across the entire archive. `memory browse` uses indexed keyset pagination through all records in the active scope. Concurrent supersession may alter search ordering; restart a query when the library changes during pagination.

## Embeddings are independent and explicit

```yaml
storage: local
project_id: airframe-development
embedding:
  adapter: disabled
```

For optional local vectors:

```yaml
embedding:
  adapter: local-hash
  model: token-hash
  model_version: '1'
  dimensions: 256
```

The shipped adapter hashes lexical tokens into normalized vectors. It is deterministic, bounded and costs $0 in model API usage. It requires no credentials, downloads, numerical library or model service. It is not a learned semantic embedding model and does not promise synonym recall. Configuration has its own model/version/dimension identity, independent of the generation model. The deprecated `embeddings: true` flag and `Provider.embed` compatibility method no longer authorize paid calls; the latter returns `None`.

Vectors are disposable derived data. New records are embedded only when this adapter is explicitly configured. After changing adapter settings or dropping vectors, call `memory reindex` until its `next_cursor` is null. Each request processes at most 100 records; retrying is safe and does not modify claims or evidence status. Disabled adapters clear derived vectors. Missing vectors, mismatched identities or an unavailable Atlas vector index leave lexical retrieval working, with an explicit fallback status. The Atlas index specification is available from `memory indexes`; index provisioning is a separate explicit administration step. See [Atlas setup](atlas.md).

## CLI and HTTP operations

Start/connect to the workspace owner with `davinci service ensure`. Every CLI operation below calls that localhost service; it does not open its own Engine or write the database. Both managed and external users use these same commands and JSON contracts. Existing localhost host/origin protections apply.

| CLI | HTTP operation |
| --- | --- |
| `memory search QUERY --experiment ID` | POST `/api/v2/memory/search` (`MemorySearch`) |
| `memory browse --limit 50 --cursor ID` | GET `/api/v2/memory/records` (`after_id`, `limit`) |
| `memory inspect ID` | GET `/api/v2/memory/records/ID` |
| `memory note --file note.json` | POST `/api/v2/memory/notes` (`MemoryNote`) |
| `memory supersede ID --file correction.json` | POST `/api/v2/memory/records/ID/supersede` (`Supersession`) |
| `memory exact --file exact-inputs.json` | POST `/api/v2/memory/exact` (`ExactInputs`) |
| `memory export --ids ID ... --output memory.json` | POST `/api/v2/memory/export` (`MemoryExport`) |
| `memory import --file memory.json --actor agent --operation-id import-1` | POST `/api/v2/memory/import` (`MemoryImport`) |
| `memory capture --experiment ID --result RESULT_ID` | POST `/api/v2/memory/capture` (committed result IDs only) |
| `memory reindex --cursor ID` | POST `/api/v2/memory/reindex` (`after_id`) |
| `memory indexes` | GET `/api/v2/memory/indexes` |

`memory search --context applicability.json` can provide explicit target applicability, including material/process/load ranges. Without it, an experiment's declared plan supplies the target context. No target context means applicability remains unconfirmed. Search also accepts `--limit`, `--cursor`, `--reject-incompatible` and `--include-superseded`.

Example note (replace the experiment ID):

```json
{
  "actor": "coding-agent",
  "operation_id": "section-depth-note-1",
  "experiment_id": "experiment-...",
  "kind": "lesson",
  "claim": "Increasing section depth may reduce this bracket's bending displacement; test mass and fixed interfaces again.",
  "applicability": {
    "domain": "mechanical",
    "phenomena": ["linear_static"],
    "materials": ["aluminium"],
    "material_models": ["linear_isotropic"],
    "load_regimes": ["static"]
  }
}
```

Optional `source` selects a result/candidate/test/tool from the experiment. The service verifies those references, but never promotes the note's causal claim. A correction JSON contains `actor`, `operation_id`, the old record's `revision`, `replacement_id`, and `reason`.

Notes and imports use stable operation IDs. Same key/payload reuses the record or import receipt; different content conflicts. Supersession uses revisions and idempotent retry. Capture is idempotent by committed result identity and cannot accept caller-supplied measurements. It can repair an interrupted memory projection after execution evidence was already committed. Failures in memory indexing cannot turn completed physical evidence into a missing run result. CLI output remains the existing JSON envelope and exit-code contract.

## Portable export/import

Exports default to references only. Add `--include-artifacts` to include verified base64 artifact payloads. Portable artifact payloads are limited to 8 MB before encoding; imports are limited to 16 MB, 100 records and 300 blobs. Individual stored experience records are limited to 2 MB. Larger solver fields stay in the normal artifact store: export references and report the missing portable evidence explicitly rather than truncating it silently.

Import checks payload sizes, SHA-256, identity and safe artifact storage paths/content metadata. Corrupted supplied bytes reject the import. Missing/invalid references are recorded in `evidence_issues`; they do not create local evidence. Export relevant replacement records together to resolve supersession links. Imported records keep origin, source support, provenance and prior history, while acquiring a destination scope and `imported_unverified` status. They are excluded from exact local evidence even if matching bytes happen to exist locally. Imported source claims are not cryptographically authenticated; checksum integrity is not scientific validation.

## Compatibility and benchmark

No historical records are rewritten and no database migration is required. New tables/indexes are rebuildable projections for the new collection. Existing `memories`, policy history and archived studies remain intact. Unscoped historical records are not automatically adopted into cross-project search or exact evidence. Use an explicit note/import with source provenance; do not retrospectively label old runs as test-first or locally reproduced. Old opening-operation IDs that would collide with an unscoped experiment require inspection and a new scoped operation ID. Existing experiment IDs remain readable. New linked runs have explicit scope.

The small authored [retrieval benchmark](memory-benchmark.json) uses 11 corpus records and four separate held-out queries through public HTTP operations. It includes failures of reasoning, incompatible applicability and a superseded false lesson. All claims are synthetic hypotheses. It reports precision@3, recall@3, relevant-query coverage and misleading suggestions. The recorded run found relevant hits for 4/4 queries, precision@3 0.50 and recall@3 1.00, with one misleading hypothesis among seven returned suggestions. That false inference survives declared-metadata filtering and still needs review. These results do not measure or prove design improvement.

```bash
uv run pytest -m 'not integration' -q
uv run python scripts/memory_benchmark.py --output /tmp/memory-benchmark.json
DAVINCI_INTEGRATION=1 uv run pytest tests/product/test_external_cli.py -m integration -q
```

The native integration uses actual CAD/beam evaluation, then searches the observations, performs exact evidence inspection and exports/imports artifacts through the public CLI. No paid generation, embedding service or private database is used by these tests.
