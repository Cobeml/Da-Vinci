"""Provision validators and indexes in the configured Atlas database."""

import json
from pathlib import Path

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from davinci.config import Settings


def main():
    settings = Settings()
    if not settings.mongodb_uri:
        raise SystemExit("Set MONGODB_URI in .env; no URI was supplied.")
    db = MongoClient(settings.mongodb_uri)[settings.mongodb_database]
    required = {
        "candidates": [
            "_id",
            "run_id",
            "source_commit",
            "source_bundle_artifact_id",
            "specification_id",
            "parameters",
            "subsystem",
        ],
        "evaluations": [
            "_id",
            "candidate_id",
            "run_id",
            "evaluator_version",
            "outcome",
            "metrics",
            "violations",
        ],
        "tools": ["_id", "source_commit", "status", "input_schema", "output_schema", "validation"],
        "policies": ["_id", "content", "source_commit"],
        "jobs": ["_id", "job_key", "kind", "status", "run_id", "lease_expires_at"],
        "memories": ["_id", "candidate_id", "evaluation_id", "summary", "outcome", "embedding_version"],
    }
    for name, fields in required.items():
        validator = {
            "$jsonSchema": {
                "bsonType": "object",
                "required": fields,
                "properties": {"_id": {"bsonType": "string"}},
            }
        }
        if name in db.list_collection_names():
            db.command("collMod", name, validator=validator, validationLevel="strict")
        else:
            db.create_collection(name, validator=validator)
    db.jobs.create_index("job_key", unique=True)
    db.jobs.create_index([("status", 1), ("lease_expires_at", 1), ("created_at", 1)])
    db.candidates.create_index([("project_id", 1), ("run_id", 1), ("created_at", -1)])
    db.evaluations.create_index([("candidate_id", 1), ("evaluator_version", 1)], unique=True)
    db.tools.create_index([("project_id", 1), ("name", 1), ("version", 1)], unique=True)
    db.memories.create_index([("fingerprint", 1), ("outcome", 1)])
    db.events.create_index([("run_id", 1), ("created_at", 1)])
    definition = json.loads(Path("atlas/vector-index.json").read_text())
    existing = {index["name"] for index in db.memories.list_search_indexes()}
    if definition["name"] not in existing:
        db.memories.create_search_index(SearchIndexModel(**definition))
    print("Validators and indexes configured. Wait for memory_vector to become READY in Atlas.")
    print("Install the two INSERT-only triggers from atlas/ and set DAVINCI_DATABASE to the database name.")


if __name__ == "__main__":
    main()
