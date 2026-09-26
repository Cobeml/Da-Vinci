"""Provision validators and indexes in the configured Atlas database."""

import argparse
import json
import time
from pathlib import Path

from pymongo import MongoClient
from pymongo.operations import SearchIndexModel

from davinci.config import Settings


def provision(settings, wait_seconds=600):
    if not settings.mongodb_uri:
        raise SystemExit("Set MONGODB_URI in .env; no URI was supplied.")
    client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=12000, socketTimeoutMS=30000)
    db = client[settings.mongodb_database]
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
            existing = db[name].options()
            if existing.get("validator") != validator or existing.get("validationLevel", "strict") != "strict":
                raise RuntimeError(f"Existing {name} validator differs; inspect before changing it")
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
    existing = {index["name"]: index for index in db.memories.list_search_indexes()}
    if definition["name"] in existing:
        actual = existing[definition["name"]]
        if actual.get("latestDefinition") != definition["definition"] or actual.get("type") != definition["type"]:
            raise RuntimeError("Existing memory_vector definition differs; inspect before changing it")
    else:
        db.memories.create_search_index(SearchIndexModel(**definition))
    print("Validators and indexes configured; waiting for memory_vector.", flush=True)
    deadline = time.monotonic() + wait_seconds
    while True:
        indexes = list(db.memories.list_search_indexes(definition["name"]))
        if indexes and indexes[0].get("queryable") and indexes[0].get("status") == "READY":
            break
        if indexes and indexes[0].get("status") == "FAILED":
            raise RuntimeError("memory_vector provisioning failed")
        if time.monotonic() >= deadline:
            raise TimeoutError("memory_vector did not become READY within the allotted time")
        print("memory_vector is still provisioning", flush=True)
        time.sleep(10)
    print("memory_vector is READY and queryable.", flush=True)
    client.close()
    print("Install the two INSERT-only triggers from atlas/ and set DAVINCI_DATABASE to the database name.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-seconds", type=int, default=600)
    args = parser.parse_args()
    try:
        provision(Settings(), args.wait_seconds)
    except Exception as exc:
        # Never print driver exceptions: they can contain the connection URI.
        print(json.dumps({"stage": "atlas_setup", "status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
