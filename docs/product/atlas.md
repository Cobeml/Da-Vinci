# MongoDB Atlas for Scalable Model Improvement

Local SQLite and artifacts are the default. Select Atlas explicitly in a separate workspace:

```yaml
storage: atlas
database: da_vinci_product
project_id: airframe-development
embedding:
  adapter: disabled
```

Supply `MONGODB_URI` through the environment or workspace `.env`. `OPENAI_API_KEY` is only needed for managed live reasoning. Memory and external lifecycle operations need no model key. The shipped optional embedding adapter runs locally with no paid service or download. Configure Atlas network access for the host's actual outbound IP, not its Tailscale address unless routing intentionally exits through that address.

Use a dedicated product database, not the historical `da_vinci` study database. The product still supports one server per workspace/database; shared simultaneous workspace execution is not supported. Memory records are additionally filtered by workspace and active project. Cross-object retrieval stays within both boundaries. Cross-project transfer uses explicit portable export/import, with imported evidence marked unverified locally.

Documents hold runs, candidates, evaluations, policies, tools, request checkpoints and accounting. The new typed memory collection is `experiences_v1`; import idempotency receipts use `memory_operations_v1`. GridFS and the local cache hold checksummed simulation evidence. The service creates scoped metadata/exact/text indexes for the new experience collection; its database role needs index-creation permission. Existing historical collections and their validators/indexes are not rewritten. The worker executes the loop directly; Atlas Database Triggers are not required for the product.

## Optional Vector Search

For local hashed lexical vectors, set:

```yaml
embedding:
  adapter: local-hash
  model: token-hash
  model_version: '1'
  dimensions: 256
```

This is a deterministic lexical representation, not a learned semantic model. It has no model API cost or credentials. Generation-model configuration is independent. The older `embeddings: true` option no longer enables OpenAI embedding calls.

`davinci memory indexes` returns the current explicit index specification. Create its Vector Search index named `experience_vector_v1` on `experiences_v1`:

```json
{
  "fields": [
    {"type": "vector", "path": "embedding", "numDimensions": 256, "similarity": "cosine"},
    {"type": "filter", "path": "workspace_id"},
    {"type": "filter", "path": "project_id"},
    {"type": "filter", "path": "embedding_id"}
  ]
}
```

Dimensions must match the configured adapter. Model/version/dimension identity is also applied as a query filter. The query retains Atlas `vectorSearchScore` in `semantic_score`, combines it with lexical and applicability/evidence scores, and exposes the ranking components. Missing/mismatched vectors or an unavailable vector index leave scoped text retrieval usable and report a fallback status. Missing Atlas connectivity itself does not silently switch persistence to SQLite.

After changing vector settings, explicitly rebuild derived vectors with `davinci memory reindex`, following `next_cursor` until null. Rebuild or replace the Atlas index definition explicitly when dimensions change. No index or cloud service is provisioned automatically by a search. Existing historical `product_memory` / `memory_vector` indexes are not required by the new route and are left unchanged. `scripts/atlas_setup.py` still belongs to the archived hackathon environment; do not run it against a product database to configure this feature.

See [engineering memory](memory.md) for contracts, scope, portable artifacts, exact evidence isolation and benchmark results. Live Atlas/GridFS checks require an explicitly authorized database; default automated tests use SQLite and deterministic vector-boundary fixtures.
