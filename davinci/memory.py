import json
import math
import re

from davinci.models import digest, document


class Memory:
    def __init__(self, store, embed=None):
        self.store, self.embed = store, embed

    def remember(self, candidate, evaluation):
        summary = json.dumps({"subsystem": candidate["subsystem"], "parameters": candidate["parameters"],
            "outcome": evaluation["outcome"], "violations": evaluation["violations"],
            "metrics": evaluation["metrics"], "fidelity": evaluation["fidelity"]}, sort_keys=True)
        doc = {**document("memory"), "_id": "memory-"+evaluation["_id"], "project_id": candidate["project_id"],
               "run_id": candidate["run_id"], "subsystem": candidate["subsystem"],
               "specification_id": candidate["specification_id"], "evaluator_version": candidate["evaluator_version"],
               "candidate_id": candidate["_id"], "evaluation_id": evaluation["_id"],
               "parameters": candidate["parameters"], "fingerprint": candidate["fingerprint"],
               "outcome": evaluation["outcome"], "summary": summary, "embedding_version": 1,
               "embedding_status": "pending" if self.embed else "local_lexical", "embedding_model": "text-embedding-3-small"}
        if self.store.insert("memories", doc) and self.embed:
            try:
                embedding = self.embed(summary, candidate["run_id"])
                self.store.update("memories", doc["_id"], {"embedding": embedding, "embedding_status": "ready"})
            except Exception as exc:
                self.store.event(candidate["run_id"], "embedding_pending", "Embedding pending; recent evidence remains available", error=type(exc).__name__)
        return doc

    def search(self, subsystem, query, parameters=None, run_id=None):
        filters = {"project_id": "uas-demo", "subsystem": subsystem, "specification_id": "spec-demo-v1", "evaluator_version": "screening-v1"}
        recent = self.store.list("memories", filters, limit=200, reverse=True)
        if self.embed and self.store.db is not None and run_id:
            try:
                vector = self.embed(query, run_id)
                hits = list(self.store.db.memories.aggregate([{"$vectorSearch": {
                    "index": "memory_vector", "path": "embedding", "queryVector": vector,
                    "numCandidates": 100, "limit": 16, "filter": {**filters, "embedding_version": 1}}}]))
                recent = list({m["_id"]: m for m in hits+recent[:8]}.values())
            except Exception as exc:
                self.store.event(run_id, "memory_fallback", "Vector query unavailable; using recent structured evidence", error=type(exc).__name__)
        tokens = set(re.findall(r"[a-z_]+", query.lower()))

        def score(item):
            semantic = len(tokens & set(re.findall(r"[a-z_]+", item["summary"].lower())))
            distance = sum(abs(float(v)-float(item["parameters"].get(k, v)))/max(abs(float(v)), 1) for k,v in (parameters or {}).items())
            return semantic-distance
        chosen = []
        for outcome in ("passed", "failed"):
            chosen.extend(sorted([m for m in recent if m["outcome"] == outcome], key=score, reverse=True)[:4])
        return [{k:v for k,v in m.items() if k != "embedding"} for m in chosen]

    def failed_before(self, fingerprint):
        return bool(self.store.list("memories", {"fingerprint": fingerprint, "outcome": "failed"}, limit=1))
