"""Small document repository: Atlas in live mode, durable SQLite for local replay."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from davinci.errors import safe_error
from davinci.models import document, identity, now


def matches(doc, query):
    for key, wanted in query.items():
        actual = doc
        for part in key.split("."):
            actual = actual.get(part) if isinstance(actual, dict) else None
        if isinstance(wanted, dict):
            for op, value in wanted.items():
                if op == "$in" and actual not in value:
                    return False
                if op == "$lte" and (actual is None or actual > value):
                    return False
                if op == "$ne" and actual == value:
                    return False
        elif actual != wanted:
            return False
    return True


class Store:
    def __init__(self, root: Path, uri: str = "", database: str = "da_vinci"):
        self.lock = threading.RLock()
        self.mongo = MongoClient(uri, serverSelectionTimeoutMS=5000) if uri else None
        self.db = self.mongo[database] if self.mongo is not None else None
        if self.db is None:
            root.mkdir(parents=True, exist_ok=True)
            self.sql = sqlite3.connect(root / "ledger.sqlite3", check_same_thread=False, timeout=30)
            self.sql.execute("PRAGMA journal_mode=WAL")
            self.sql.execute(
                "CREATE TABLE IF NOT EXISTS documents (collection TEXT, id TEXT, body TEXT, PRIMARY KEY(collection,id))"
            )
            self.sql.commit()

    @property
    def backend(self):
        return "atlas" if self.db is not None else "sqlite-local"

    def get(self, collection, id):
        if self.db is not None:
            return self.db[collection].find_one({"_id": id})
        with self.lock:
            row = self.sql.execute(
                "SELECT body FROM documents WHERE collection=? AND id=?", (collection, id)
            ).fetchone()
            return json.loads(row[0]) if row else None

    def insert(self, collection, doc):
        doc = json.loads(json.dumps(doc, allow_nan=False))
        if self.db is not None:
            try:
                self.db[collection].insert_one(doc)
                return True
            except DuplicateKeyError:
                return False
        with self.lock:
            cursor = self.sql.execute(
                "INSERT OR IGNORE INTO documents VALUES (?,?,?)", (collection, doc["_id"], json.dumps(doc))
            )
            self.sql.commit()
            return cursor.rowcount == 1

    def list(self, collection, query=None, limit=1000, reverse=False):
        query = query or {}
        if self.db is not None:
            return list(
                self.db[collection]
                .find(query)
                .sort([("created_at", -1 if reverse else 1), ("_id", 1)])
                .limit(limit)
            )
        with self.lock:
            docs = [
                json.loads(r[0])
                for r in self.sql.execute("SELECT body FROM documents WHERE collection=?", (collection,))
            ]
        docs = [d for d in docs if matches(d, query)]
        return sorted(docs, key=lambda d: (d.get("created_at", ""), d["_id"]), reverse=reverse)[:limit]

    def update(self, collection, id, fields, expected=None):
        """Atomic compare-and-set. Never use this for immutable evidence collections."""
        expected = expected or {}
        if self.db is not None:
            return self.db[collection].find_one_and_update(
                {"_id": id, **expected}, {"$set": fields}, return_document=ReturnDocument.AFTER
            )
        with self.lock:
            self.sql.execute("BEGIN IMMEDIATE")
            try:
                row = self.sql.execute(
                    "SELECT body FROM documents WHERE collection=? AND id=?", (collection, id)
                ).fetchone()
                doc = json.loads(row[0]) if row else None
                if not doc or not matches(doc, expected):
                    self.sql.rollback()
                    return None
                doc.update(fields)
                self.sql.execute(
                    "UPDATE documents SET body=? WHERE collection=? AND id=?",
                    (json.dumps(doc, allow_nan=False), collection, id),
                )
                self.sql.commit()
                return doc
            except Exception:
                self.sql.rollback()
                raise

    def mutate(self, collection: str, id: str, fn: Callable):
        for _ in range(50):
            old = self.get(collection, id)
            if old is None:
                raise KeyError(id)
            revision = old.get("revision", 0)
            fields = fn(json.loads(json.dumps(old)))
            fields["revision"] = revision + 1
            result = self.update(collection, id, fields, {"revision": revision})
            if result:
                return result
        raise RuntimeError("Concurrent modification did not settle")

    def event(self, run_id, kind, message, **data):
        event = document("event", run_id=run_id, kind=kind, message=message, data=data)
        self.insert("events", event)
        return event

    def enqueue(self, kind, subject_id, run_id):
        key = f"{kind}:{subject_id}"
        job = document(
            "job",
            job_key=key,
            kind=kind,
            subject_id=subject_id,
            run_id=run_id,
            status="pending",
            attempt=0,
            lease_token=None,
            lease_expires_at=now(),
        )
        job["_id"] = key
        self.insert("jobs", job)
        return job["_id"]

    def claim(self, seconds=180):
        candidates = self.list("jobs", {"status": {"$in": ["pending", "running"]}}, limit=10000)
        for job in candidates:
            if job["status"] == "running" and job["lease_expires_at"] > now():
                continue
            run = self.get("runs", job["run_id"])
            if run and run["status"] in ("stopped", "failed", "completed", "budget_exhausted"):
                self.update("jobs", job["_id"], {"status": "cancelled"})
                continue
            token = identity("lease")
            result = self.update(
                "jobs",
                job["_id"],
                {
                    "status": "running",
                    "lease_token": token,
                    "attempt": job["attempt"] + 1,
                    "lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(),
                },
                {"status": job["status"], "lease_token": job["lease_token"]},
            )
            if result:
                return result
        return None

    def finish(self, job, error=None):
        return self.update(
            "jobs",
            job["_id"],
            {
                "status": ("pending" if job["attempt"] < 3 else "dead") if error else "done",
                "last_error": safe_error(error) if error else None,
                "finished_at": now(),
            },
            {"lease_token": job["lease_token"], "status": "running"},
        )

    def owns(self, job):
        current = self.get("jobs", job["_id"])
        return (
            current
            and current["status"] == "running"
            and current["lease_token"] == job["lease_token"]
            and current["lease_expires_at"] > now()
        )

    def renew(self, job):
        return self.update(
            "jobs",
            job["_id"],
            {"lease_expires_at": (datetime.now(timezone.utc) + timedelta(seconds=180)).isoformat()},
            {"lease_token": job["lease_token"], "status": "running"},
        )
