"""Build a credential-free demo snapshot and controlled CAD release comparison.

Reads existing exports; never instantiates Engine, connects to Atlas, or calls a model.
"""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from davinci.config import Settings
from davinci.runner import Runner

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "docs/demo"
VALIDATION = ROOT / "runtime/validation"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bundle(name):
    path = VALIDATION / f"{name}.zip"
    with ZipFile(path) as z:
        for item in json.loads(z.read("artifact-manifest.json")):
            assert sha(z.read(f"artifacts/{item['_id']}/{item['name']}")) == item["sha256"]
        data = {name: json.loads(z.read(name + ".json")) for name in (
            "run", "specification", "candidates", "evaluations", "assemblies", "releases", "tools"
        )}
    data["zip_sha256"] = sha(path.read_bytes())
    return data


def snapshot():
    DEST.mkdir(parents=True, exist_ok=True)
    runs = {name: bundle(name) for name in ("replay", "live1", "live3")}
    report = json.loads((VALIDATION / "report.json").read_text())
    checks = report["checks"]
    # Explicit allowlist: no application settings or credentials enter this file.
    evidence = {
        "schema_version": 1,
        "accepted_at": checks["acceptance"]["checked_at"],
        "source_report_sha256": sha((VALIDATION / "report.json").read_bytes()),
        "checks": {k: checks[k] for k in (
            "reflection", "promoted_release_reuse", "budget", "triggers", "vector"
        )},
        "runs": {},
    }
    for name, data in runs.items():
        evidence["runs"][name] = {
            "run_id": data["run"]["_id"], "zip_sha256": data["zip_sha256"],
            "evaluations": data["evaluations"], "assemblies": data["assemblies"],
            "candidates": [{k: c[k] for k in (
                "_id", "parameters", "subsystem", "round", "source_commit", "release_id",
                "tool_version_ids", "specification_id", "evaluator_version"
            )} for c in data["candidates"]],
        }
    evidence["release"] = next(r for r in runs["live3"]["releases"]
                               if r["_id"] == checks["reflection"]["release_id"])
    evidence["tool"] = next(t for t in runs["live3"]["tools"]
                            if t["_id"] == checks["reflection"]["tool_id"])
    (DEST / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("Verified exported artifact hashes; wrote credential-free evidence snapshot.", flush=True)
    return runs, evidence


def compare(runs, evidence):
    # Prevent inherited connection settings from reaching even this isolated runner.
    for key in list(os.environ):
        if key.startswith(("DAVINCI_", "MONGODB_", "OPENAI_")):
            del os.environ[key]
    settings = Settings(_env_file=None, davinci_data_dir=ROOT / "runtime/demo-comparison")
    runner = Runner(settings)
    replay = runs["replay"]
    baseline = next(r for r in runs["live3"]["releases"] if r["_id"] == "release-baseline")
    promoted = evidence["release"]
    # Archive failures plus passing controls. Candidate source remains fixed across arms.
    cases = [c for c in replay["candidates"] if c["round"] in (0, 2)]
    results = []
    image = runner.image_digest()
    expected_images = {e["runtime_image_digest"] for e in replay["evaluations"]}
    if expected_images != {image}:
        raise RuntimeError("CAD image differs from archived evaluator; rebuild the pinned image first")
    for label, release in (("baseline", baseline), ("promoted", promoted)):
        adapted = runner.adapt(release["files"], cases)
        for case, parameters in zip(cases, adapted, strict=True):
            evaluated, artifacts, duration = runner.evaluate(
                case["source"], parameters, case["subsystem"], replay["specification"]
            )
            results.append({
                "arm": label, "release_id": release["_id"], "candidate_id": case["_id"],
                "subsystem": case["subsystem"], "case": "failure" if case["round"] == 0 else "control",
                "source_sha256": sha(case["source"].encode()), "source_commit": case["source_commit"],
                "input_parameters": case["parameters"], "adapted_parameters": parameters,
                "evaluation": evaluated, "duration_seconds": duration,
                "geometry_sha256": {k: sha(v) for k, v in artifacts.items() if k != "execution.log"},
            })
            print(f"{label}: {case['subsystem']} round {case['round']} -> {evaluated['outcome']}", flush=True)
    comparison = {
        "created_at": datetime.now(timezone.utc).isoformat(), "model_calls": 0,
        "method": "Paired intervention on archived release files; identical source, input, specification and image",
        "runtime_image_digest": image, "specification": replay["specification"],
        "release_files_sha256": {r["_id"]: sha(json.dumps(r["files"], sort_keys=True).encode())
                                 for r in (baseline, promoted)},
        "results": results,
    }
    (DEST / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Run eight local Docker CAD evaluations")
    args = parser.parse_args()
    runs, evidence = snapshot()
    if args.compare:
        compare(runs, evidence)


if __name__ == "__main__":
    main()
