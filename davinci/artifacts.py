import fcntl
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

import gridfs

from davinci.models import document


class Artifacts:
    def __init__(self, root, store):
        self.root = Path(root) / "artifacts"
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = store
        self.fs = gridfs.GridFSBucket(store.db) if store.db is not None else None

    def put(self, data: bytes, name: str, media_type: str, **metadata):
        return self.put_stream(io.BytesIO(data), name, media_type, **metadata)

    def put_stream(self, stream, name, media_type, *, max_bytes=256_000_000, **metadata):
        """Bounded streaming ingest shared by local files and optional GridFS."""
        if (
            Path(name).name != name
            or name in ("", ".", "..")
            or "\\" in name
            or any(ord(c) < 32 for c in name)
        ):
            raise ValueError("Invalid artifact name")
        if not re.fullmatch(r"[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+", media_type):
            raise ValueError("Invalid artifact media type")
        # Provenance belongs in manifests; storage identity/integrity cannot be overridden.
        if set(metadata) & {"_id", "sha256", "size", "gridfs_id", "name", "media_type"}:
            raise ValueError("Reserved artifact metadata")
        sha, size = hashlib.sha256(), 0
        with tempfile.NamedTemporaryFile(dir=self.root, prefix=".upload-", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            try:
                while chunk := stream.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Artifact quota exceeded")
                    sha.update(chunk)
                    temporary.write(chunk)
                temporary.flush()
                checksum = sha.hexdigest()
                identity = "artifact-" + checksum
                if self.store.get("artifacts", identity):
                    return identity
                path = self.root / checksum
                if path.is_symlink():
                    raise ValueError("Artifact symlink rejected")
                temporary_path.replace(path)
                file_id = None
                if self.fs is not None:
                    with path.open("rb") as data:
                        file_id = str(self.fs.upload_from_stream(name, data, metadata={"sha256": checksum}))
                self.store.insert(
                    "artifacts",
                    {
                        **document("artifact"),
                        "_id": identity,
                        "sha256": checksum,
                        "name": name,
                        "media_type": media_type,
                        "size": size,
                        "gridfs_id": file_id,
                        **metadata,
                    },
                )
                return identity
            finally:
                temporary_path.unlink(missing_ok=True)

    def verified_open(self, identity, max_bytes=256_000_000):
        """Verify the entire artifact before returning a seekable stream or HTTP headers.

        Spools to disk above 1 MB. O_NOFOLLOW and fstat reject symlinks/FIFOs.
        """
        record = self.store.get("artifacts", identity)
        if not record:
            raise KeyError(identity)
        if not re.fullmatch(r"[a-f0-9]{64}", record["sha256"]) or record["size"] > max_bytes:
            raise ValueError("Invalid artifact checksum or size")
        path = self.root / record["sha256"]
        if not path.exists() and not path.is_symlink() and self.fs is not None:
            from bson import ObjectId

            source = self.fs.open_download_stream(ObjectId(record["gridfs_id"]))
        else:
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except OSError as exc:
                raise ValueError("Artifact missing or unsafe path") from exc
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                os.close(fd)
                raise ValueError("Artifact is not a regular file")
            source = os.fdopen(fd, "rb")
        spool = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
        sha, size = hashlib.sha256(), 0
        try:
            with source:
                while chunk := source.read(1024 * 1024):
                    size += len(chunk)
                    if size > max_bytes or size > record["size"]:
                        raise ValueError("Artifact size/checksum mismatch")
                    sha.update(chunk)
                    spool.write(chunk)
            if size != record["size"] or sha.hexdigest() != record["sha256"]:
                raise ValueError("Artifact checksum mismatch")
            spool.seek(0)
            return spool
        except Exception:
            spool.close()
            raise

    def read(self, identity):
        with self.verified_open(identity) as stream:
            return stream.read()

    def verify(self, identity):
        with self.verified_open(identity):
            pass

    def chunks(self, verified_stream):
        try:
            while chunk := verified_stream.read(1024 * 1024):
                yield chunk
        finally:
            verified_stream.close()


class Repository:
    """Permanent append-only source snapshots; all writes are serialized across processes."""

    def __init__(self, root):
        self.path = Path(root) / "repository"
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(root) / "repository.lock"

    def _git(self, *args):
        return subprocess.check_output(
            [
                "git",
                "-C",
                str(self.path),
                "-c",
                "user.name=Da Vinci",
                "-c",
                "user.email=harness@localhost",
                *args,
            ],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()

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
