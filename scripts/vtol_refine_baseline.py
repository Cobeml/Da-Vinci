"""Precompute baseline convergence while the design model works; no API/Atlas access."""

import json
from pathlib import Path

from davinci.config import Settings
from davinci.runner import Runner
from davinci.vtol import REFERENCE_SOURCE, evaluate
from sandbox.vtol_family import BASELINE
from scripts.vtol_study import STUDY

if __name__ == "__main__":
    root = Path("runtime") / STUDY
    runner = Runner(Settings(_env_file=None))
    for resolution in (14, 18):
        key = f"{STUDY}-00-r{resolution}"
        path = root / (key + "-evaluation.json")
        out = root / (key + "-artifacts")
        out.mkdir(exist_ok=True)
        if not path.exists():
            result, files = evaluate(runner, REFERENCE_SOURCE, BASELINE, resolution)
            for name, data in files.items():
                (out / name).write_bytes(data)
            path.write_text(json.dumps(result))
        result = json.loads(path.read_text())
        print(
            resolution, result["outcome"], {k: v["value"] for k, v in result["metrics"].items()}, flush=True
        )
