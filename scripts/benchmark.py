"""Benchmark ten trusted sample candidates with one and two CAD workers."""

import json
import time
from concurrent.futures import ThreadPoolExecutor

from davinci.config import Settings
from davinci.models import SPECIFICATION
from davinci.runner import Runner
from davinci.templates import MOUNT_SOURCE, WING_SOURCE


def main():
    settings = Settings()
    results = []
    for workers in (1, 2):

        def evaluate(index):
            runner = Runner(settings)
            structural = index % 2 == 0
            result, _, duration = runner.evaluate(
                MOUNT_SOURCE if structural else WING_SOURCE,
                {"thickness_mm": 3.0}
                if structural
                else {"span_mm": 600, "hinge_gap_mm": 2, "flap_fraction": 0.25},
                "structural" if structural else "aerodynamic",
                SPECIFICATION,
            )
            if result["outcome"] != "passed":
                raise RuntimeError(result["violations"])
            return {
                "duration_seconds": round(duration, 3),
                "evaluator_peak_rss_mb": round(result["peak_rss_mb"], 1),
            }

        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            samples = list(pool.map(evaluate, range(10)))
        report = {
            "workers": workers,
            "samples": samples,
            "wall_seconds": round(time.monotonic() - started, 3),
            "container_limit": {"cpus": 2, "memory_gib": 4},
        }
        results.append(report)
        print(json.dumps(report), flush=True)
    (settings.root / "benchmark.json").write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
