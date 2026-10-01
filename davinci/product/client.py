"""Local HTTP client. Never imports Engine, Store, Runner, or a model provider."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from davinci.models import digest
from davinci.product.config import workspace_settings


class ClientError(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


class Client:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        self.base = f"http://127.0.0.1:{workspace_settings(self.workspace).port}"
        # Ignore ambient proxies for the localhost control boundary.
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, method, path, body=None, *, binary=False):
        if not path.startswith("/api/") or "?" in path.split("/api/", 1)[0]:
            raise ClientError("Only local API paths are supported", 2)
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(body, allow_nan=False).encode() if body is not None else None,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.http.open(request, timeout=30) as response:
                return response.read() if binary else json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                message = json.load(exc).get("detail", f"HTTP {exc.code}")
            except (ValueError, AttributeError):
                message = f"HTTP {exc.code}"
            raise ClientError(
                str(message), {404: 5, 409: 4, 422: 2, 403: 2, 415: 2}.get(exc.code, 1)
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ClientError(
                "Service unavailable or request timed out. Run davinci service ensure; inspect status before retrying a mutation.",
                3,
            ) from None

    def connect(self):
        health = self.request("GET", "/api/v1/health")
        if health.get("workspace_id") != digest(str(self.workspace)):
            raise ClientError(
                "This port serves another workspace. Choose a different port in workspace.yaml.", 4
            )
        return health

    def status(self, eid):
        from urllib.parse import quote

        return self.request("GET", "/api/v2/experiments/" + quote(eid, safe=""))

    def mutate(self, eid, action, payload, operation_id, *, actor=None, revision=None):
        from urllib.parse import quote

        row = self.status(eid)
        if row["driver"] != "external":
            raise ClientError("External CLI operations require an external experiment", 4)
        body = {
            "actor": actor or row["actor"],
            "revision": row["revision"] if revision is None else revision,
            "operation_id": operation_id,
            **payload,
        }
        return self.request("POST", f"/api/v2/experiments/{quote(eid, safe='')}/{action}", body)

    def wait(self, eid, job_id, timeout=300):
        from urllib.parse import quote

        deadline = time.monotonic() + timeout
        while True:
            job = self.request(
                "GET", f"/api/v2/experiments/{quote(eid, safe='')}/jobs/{quote(job_id, safe='')}"
            )
            if job["status"] not in ("queued", "running"):
                return job
            if time.monotonic() >= deadline:
                return {**job, "wait_timed_out": True}
            time.sleep(min(0.2, max(0, deadline - time.monotonic())))

    def download(self, artifact_id, destination):
        from urllib.parse import quote

        data = self.request("GET", "/api/v1/artifacts/" + quote(artifact_id, safe=""), binary=True)
        if artifact_id != "artifact-" + hashlib.sha256(data).hexdigest():
            raise ClientError("Artifact checksum mismatch")
        Path(destination).write_bytes(data)
        return {"artifact_id": artifact_id, "path": str(Path(destination).resolve()), "bytes": len(data)}
