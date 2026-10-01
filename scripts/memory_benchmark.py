"""Reproducible held-out retrieval fixture using only the public localhost API."""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from davinci.models import digest
from davinci.product.client import Client
from davinci.product.tasks import RESOURCES


def exercise(client, data):
    source = client.request(
        "POST",
        "/api/v2/experiments",
        {
            "object": {"slug": "reference-library", "name": "Reference library"},
            "description": "Synthetic retrieval corpus",
            "driver": "external",
            "actor": "benchmark",
            "operation_id": "source",
        },
    )
    target = client.request(
        "POST",
        "/api/v2/experiments",
        {
            "object": {"slug": "held-out-component", "name": "Held-out component"},
            "description": "Held-out retrieval requests",
            "driver": "external",
            "actor": "benchmark",
            "operation_id": "target",
        },
    )

    def context(item):
        return {
            "domain": item["domain"],
            "materials": [item["material"]],
            "phenomena": item["phenomena"],
            "load_regimes": [item["regime"]],
        }

    ids = {}
    for item in data["corpus"]:
        result = client.request(
            "POST",
            "/api/v2/memory/notes",
            {
                "actor": "benchmark",
                "operation_id": item["id"],
                "experiment_id": source["_id"],
                "claim": item["claim"],
                "applicability": context(item),
            },
        )
        ids[item["id"]] = result["id"]
    for item in data["corpus"]:
        if item.get("superseded_by"):
            client.request(
                "POST",
                "/api/v2/memory/records/" + ids[item["id"]] + "/supersede",
                {
                    "actor": "benchmark",
                    "operation_id": "supersede-" + item["id"],
                    "revision": 0,
                    "replacement_id": ids[item["superseded_by"]],
                    "reason": "Fixture label identifies misleading claim",
                },
            )
    reverse = {v: k for k, v in ids.items()}
    results = []
    for query in data["held_out_queries"]:
        result = client.request(
            "POST",
            "/api/v2/memory/search",
            {
                "query": query["query"],
                "experiment_id": target["_id"],
                "applicability": context(query),
                "limit": 3,
                "include_incompatible": False,
            },
        )
        returned = [reverse[item["id"]] for item in result["items"]]
        relevant = len(set(returned) & set(query["relevant"]))
        misleading_labels = set(query["misleading"]) | {
            r["id"] for r in data["corpus"] if r.get("intentionally_misleading")
        }
        misleading = len(set(returned) & misleading_labels)
        results.append(
            {
                "query": query["query"],
                "returned": returned,
                "relevant": relevant,
                "misleading": misleading,
                "precision_at_3": relevant / 3,
                "recall_at_3": relevant / len(query["relevant"]),
                "all_require_new_validation": all(
                    i["applicability_check"]["requires_new_validation"] for i in result["items"]
                ),
            }
        )
    return {
        "fixture_sha256": digest(data),
        "corpus_size": len(data["corpus"]),
        "held_out_queries": len(results),
        "precision_at_3": sum(r["precision_at_3"] for r in results) / len(results),
        "recall_at_3": sum(r["recall_at_3"] for r in results) / len(results),
        "queries_with_relevant_hit": sum(r["relevant"] > 0 for r in results),
        "misleading_suggestions": sum(r["misleading"] for r in results),
        "returned_suggestions": sum(len(r["returned"]) for r in results),
        "results": results,
        "claim": "Retrieval on a small authored fixture only; no proven design improvement or generalization claim",
        "embedding": "disabled",
        "cross_object": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.endswith("_API_KEY") and k != "MONGODB_URI" and not k.startswith("DAVINCI_PRODUCT_")
    }
    with tempfile.TemporaryDirectory(prefix="davinci-memory-benchmark-") as directory:
        root = Path(directory)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        (root / "workspace.yaml").write_text(
            f"storage: local\nproject_id: retrieval-benchmark\nport: {port}\n"
        )
        started = subprocess.run(
            [sys.executable, "-m", "davinci.product.cli", "--workspace", str(root), "service", "ensure"],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        health = json.loads(started.stdout)["data"]
        try:
            client = Client(root)
            data = json.loads(RESOURCES.joinpath("external/memory-benchmark.json").read_text())
            result = exercise(client, data)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
        finally:
            os.kill(health["started_pid"], signal.SIGTERM)


if __name__ == "__main__":
    main()
