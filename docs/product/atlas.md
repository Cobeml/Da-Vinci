# Optional MongoDB Atlas

Local storage is the default. To use Atlas, create a separate workspace and select it explicitly in `workspace.yaml`:

```yaml
storage: atlas
database: da_vinci_product
```

Supply `MONGODB_URI` and `OPENAI_API_KEY` through the environment or workspace `.env`. Configure Atlas network access for the host's actual outbound IP, not its Tailscale address unless your routing intentionally exits through that address.

Use a dedicated product database. Do not point the product at the historical `da_vinci` study database. The MVP supports one server per workspace/database; sharing one database between simultaneously running workspace servers is not supported.

Documents hold objects, runs, candidates, evaluations, policies, memories, tools, request checkpoints, and accounting. GridFS stores STEP and GLB artifacts with a local cache. The worker executes the loop directly; Atlas Database Triggers are not required and should not be added to these product collections.

## Vector Search

Create a Vector Search index named `product_memory` on the `memories` collection:

```json
{
  "fields": [
    {"type": "vector", "path": "embedding", "numDimensions": 1536, "similarity": "cosine"},
    {"type": "filter", "path": "object_id"},
    {"type": "filter", "path": "task_version"}
  ]
}
```

Only matching object/task versions are retrieved. The engine uses `text-embedding-3-small`; if embedding or vector queries fail, recent structured and lexical evidence remains available. The run records a vector-query fallback event. Missing Atlas connectivity itself does not switch persistence to SQLite.

There is no local-to-Atlas migration tool in the MVP. Choose storage when starting a workspace. Historical demos use recorded fixtures rather than importing or modifying the live database.
