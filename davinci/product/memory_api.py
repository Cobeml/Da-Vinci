"""Memory HTTP operations use the workspace owner, identical for either reasoning driver."""

from fastapi import APIRouter, Query
from pydantic import Field

from davinci.product.config import Strict
from davinci.product.memory_contracts import (
    ExactInputs,
    MemoryExport,
    MemoryImport,
    MemoryNote,
    MemorySearch,
    Supersession,
)


class Capture(Strict):
    experiment_id: str
    result_id: str


class Reindex(Strict):
    after_id: str = Field(default="", max_length=200)


def router(engine):
    api = APIRouter(prefix="/api/v2/memory")
    memory = engine.experience

    @api.post("/search")
    def search(body: MemorySearch):
        return memory.search(body)

    @api.get("/records")
    def browse(
        after_id: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=100)
    ):
        rows = engine.store.experience_page(memory.scope, limit=limit + 1, after_id=after_id)
        return {
            "items": [memory._public(r) for r in rows[:limit]],
            "next_cursor": rows[limit - 1]["_id"] if len(rows) > limit else None,
            "scope": memory.scope,
        }

    @api.get("/records/{identity}")
    def inspect(identity: str):
        return memory.get(identity, verify=True)

    @api.post("/notes", status_code=201)
    def note(body: MemoryNote):
        return memory.note(body)

    @api.post("/records/{identity}/supersede")
    def supersede(identity: str, body: Supersession):
        return memory.supersede(identity, body)

    @api.post("/exact")
    def exact(body: ExactInputs):
        return memory.exact(body)

    @api.post("/export")
    def export(body: MemoryExport):
        return memory.export(body.ids, body.include_artifacts)

    @api.post("/import")
    def import_bundle(body: MemoryImport):
        return memory.import_bundle(body)

    @api.post("/capture")
    def capture(body: Capture):
        row = memory._run(body.experiment_id)
        result = next((r for r in row.get("results", []) if r["id"] == body.result_id), None)
        if result is None:
            raise KeyError("Committed result not found")
        return memory.observe(row, result)

    @api.post("/reindex")
    def reindex(body: Reindex):
        return memory.reindex(body.after_id)

    @api.get("/indexes")
    def indexes():
        return {
            "collection": "experiences_v1",
            "name": "experience_vector_v1",
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": engine.options.embedding.dimensions,
                        "similarity": "cosine",
                    },
                    *[{"type": "filter", "path": k} for k in ("workspace_id", "project_id", "embedding_id")],
                ]
            },
            "embedding": engine.options.embedding.model_dump(),
            "automatic_provisioning": False,
        }

    return api
