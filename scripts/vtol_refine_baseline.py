"""Precompute convergence while the design model works; no API/Atlas access."""

import argparse
import json
from pathlib import Path

from davinci.config import Settings
from davinci.runner import Runner
from davinci.vtol import REFERENCE_SOURCE, evaluate
from sandbox.vtol_family import BASELINE
from scripts.vtol_study import STUDY

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iteration", type=int, default=1, help="Archived iteration, numbered from 1")
    args = parser.parse_args()
    source, parameters = REFERENCE_SOURCE, BASELINE
    if args.iteration != 1:
        manifest = json.loads(Path("web/data/vtol-gallery.json").read_text())
        if manifest["study_id"] != STUDY:
            parser.error("Gallery belongs to another evaluator cohort")
        candidate = next((d for d in manifest["designs"] if d["iteration"] == args.iteration), None)
        if not candidate:
            parser.error("Iteration is not archived yet")
        parameters = candidate["parameters"]
        source = Path(f"web/public/models/vtol/{STUDY}/{args.iteration:02d}.py").read_text()
    root = Path("runtime") / STUDY
    runner = Runner(Settings(_env_file=None))
    for resolution in (14, 18):
        key = f"{STUDY}-{args.iteration - 1:02d}-r{resolution}"
        path = root / (key + "-evaluation.json")
        out = root / (key + "-artifacts")
        out.mkdir(exist_ok=True)
        if not path.exists():
            result, files = evaluate(runner, source, parameters, resolution)
            for name, data in files.items():
                (out / name).write_bytes(data)
            path.write_text(json.dumps(result))
        result = json.loads(path.read_text())
        print(
            resolution, result["outcome"], {k: v["value"] for k, v in result["metrics"].items()}, flush=True
        )
