import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import threading

import gridfs

from davinci.models import document


class Artifacts:
    def __init__(self, root, store):
        self.root = Path(root) / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.fs = gridfs.GridFSBucket(store.db) if store.db is not None else None

    def put(self, data: bytes, name: str, media_type: str, **metadata):
        sha = hashlib.sha256(data).hexdigest()
        id = "artifact-" + sha
        existing = self.store.get("artifacts", id)
        if existing:
            return id
        path = self.root / sha
        # Atomic rename prevents readers observing incomplete artifacts.
        temporary = self.root / f".{sha}.{threading.get_ident()}"
        temporary.write_bytes(data)
        temporary.replace(path)
        file_id = None
        if self.fs is not None:
            file_id = str(self.fs.upload_from_stream(name, data, metadata={"sha256": sha}))
        self.store.insert("artifacts", {**document("artifact"), "_id": id, "sha256": sha,
            "name": Path(name).name, "media_type": media_type, "size": len(data), "gridfs_id": file_id,
            **metadata})
        return id

    def read(self, id):
        record = self.store.get("artifacts", id)
        if not record:
            raise KeyError(id)
        path = self.root / record["sha256"]
        if not path.exists() and self.fs is not None:
            from bson import ObjectId
            data = self.fs.open_download_stream(ObjectId(record["gridfs_id"])).read()
        else:
            data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != record["sha256"]:
            raise ValueError("Artifact checksum mismatch")
        return data


class Repository:
    """Permanent append-only source snapshots; all writes are serialized across processes."""
    def __init__(self, root):
        self.path = Path(root) / "repository"
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(root) / "repository.lock"

    def _git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.path), "-c", "user.name=Da Vinci",
                                        "-c", "user.email=harness@localhost", *args], stderr=subprocess.STDOUT, text=True).strip()

    def commit(self, snapshot_id, files):
        with self.lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if not (self.path / ".git").exists():
                self._git("init", "-q")
            base = self.path / "snapshots" / snapshot_id
            if base.exists():
                return self._git("log", "-1", "--format=%H", "--", str(base.relative_to(self.path)))
            for name, text in files.items():
                path = base / name
                if not path.resolve().is_relative_to(base.resolve()):
                    raise ValueError("Invalid source path")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            self._git("add", "--", str(base.relative_to(self.path)))
            self._git("commit", "-q", "-m", f"Archive {snapshot_id}")
            return self._git("rev-parse", "HEAD")

    def bundle(self, files):
        return json.dumps(files, sort_keys=True).encode()
