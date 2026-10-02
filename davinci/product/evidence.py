"""Typed artifact boundary for simulator output; payloads are never executable on the host."""

import json
from pathlib import PurePosixPath

from davinci.product.simulation_contracts import ArtifactEntry, ArtifactManifest
from davinci.runner import SandboxError

TYPES = {
    ".xml": ("application/xml", "solver_deck"),
    ".step": ("application/step", "cad"),
    ".stp": ("application/step", "cad"),
    ".glb": ("model/gltf-binary", "cad"),
    ".json": ("application/json", "result"),
    ".log": ("text/plain", "log"),
    ".txt": ("text/plain", "log"),
    ".msh": ("application/octet-stream", "mesh"),
    ".vtk": ("application/octet-stream", "fields"),
    ".vtu": ("application/octet-stream", "fields"),
    ".npz": ("application/octet-stream", "fields"),
    ".csv": ("text/csv", "fields"),
    ".inp": ("text/plain", "solver_deck"),
    ".dat": ("text/plain", "solver_deck"),
}


def content_type(name, data):
    path = PurePosixPath(name)
    if path.name != name or name.startswith(".") or "\\" in name or any(ord(c) < 32 for c in name):
        raise ValueError("Invalid simulation artifact path")
    if path.suffix not in TYPES:
        raise ValueError("Unsupported simulation artifact content type")
    media, kind = TYPES[path.suffix]
    if path.suffix == ".glb" and data[:4] != b"glTF":
        raise ValueError("Invalid GLB artifact")
    if path.suffix == ".json":
        json.loads(data)
    if name in ("bindings.json", "faces.json", "assembly-bindings.json"):
        kind = "bindings"
    elif name in ("resources.json", "solver-resources.json", "timing.json", "capability.json"):
        kind = "resources"
    elif name in ("convergence.json", "uncertainty.json"):
        kind = name.split(".")[0]
    return media, kind


def archive(artifacts, outputs, log, *, limit=256_000_000):
    refs, total = {}, 0
    omissions = []
    for name, data in {**outputs, "execution.log": log.encode()}.items():
        try:
            media, _ = content_type(name, data)
            if total + len(data) > limit:
                raise ValueError("Artifact quota exceeded")
            refs[name] = artifacts.put(data, name, media)
            total += len(data)
        except (ValueError, UnicodeError):
            # Preserve valid failure evidence; never accept a partially archived simulation.
            omissions.append(name)
    if omissions:
        refs["artifact-failure.json"] = artifacts.put(
            json.dumps({"omissions": omissions}).encode(), "artifact-failure.json", "application/json"
        )
    return refs


def manifest(artifacts, refs, provenance):
    entries, omissions = [], []
    for name, identity in refs.items():
        record = artifacts.store.get("artifacts", identity)
        base = PurePosixPath(name).name
        # Type classification does not re-read large binary payloads.
        kind = TYPES.get(PurePosixPath(base).suffix, ("application/octet-stream", "other"))[1]
        if base in ("bindings.json", "faces.json", "assembly-bindings.json"):
            kind = "bindings"
        elif base.endswith(("resources.json", "solver-resources.json", "timing.json", "capability.json")):
            kind = "resources"
        elif base in ("convergence.json", "uncertainty.json"):
            kind = base.split(".")[0]
        if base == "artifact-failure.json":
            omissions.extend(json.loads(artifacts.read(identity))["omissions"])
        if base == "resources.json":
            omissions.extend(json.loads(artifacts.read(identity)).get("omitted_outputs", []))
        entries.append(
            ArtifactEntry(
                name=name,
                artifact_id=identity,
                sha256=record["sha256"],
                size=record["size"],
                media_type=record["media_type"],
                kind=kind,
            )
        )
    return ArtifactManifest(
        provenance=provenance,
        entries=entries,
        total_bytes=sum(e.size for e in entries),
        complete=not omissions,
        omissions=omissions,
    )


def ensure_output_budget(outputs, runtime):
    if sum(len(v) for v in outputs.values()) > runtime.artifact_bytes or any(
        len(v) > runtime.file_bytes for v in outputs.values()
    ):
        raise SandboxError("Simulation artifact budget exceeded", reason="artifact_quota", outputs=outputs)
