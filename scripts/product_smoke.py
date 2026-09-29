"""Two linked sensor runs; credentials consumed internally, never printed.

Run explicitly with --live to spend at most $10 of conservative API accounting.
Default replay still builds/evaluates real CAD. Safe to rerun: completed runs are retained.
"""

import argparse
import json
from pathlib import Path

import yaml

from davinci.config import Settings
from davinci.product.engine import Engine
from davinci.product.tasks import template_config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--atlas", action="store_true")
    parser.add_argument(
        "--continue-after-fix",
        action="store_true",
        help="Archive incomplete attempts and start new linked tests; never retry their API requests",
    )
    args = parser.parse_args()
    root = Path("runtime/product-live-smoke" if args.live else "runtime/product-replay-smoke").resolve()
    if args.atlas:
        root = root.with_name(root.name + "-atlas")
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace.yaml").write_text(
        yaml.safe_dump(
            {
                "storage": "atlas" if args.atlas else "local",
                "database": "da_vinci_product_smoke",
                "daily_budget_usd": 10,
                "port": 8743,
            }
        )
    )
    engine = Engine(root, credentials=Settings() if args.live else Settings(_env_file=None))
    existing = engine.store.list("runs", limit=100)
    incomplete = [r for r in existing if r["status"] != "completed"]
    if incomplete and not args.continue_after_fix:
        raise RuntimeError("Prior smoke run incomplete; inspect its archived state before retrying.")
    for r in incomplete:
        engine.store.update(
            "runs",
            r["_id"],
            {
                "status": "failed",
                "error": "Archived API input-format failure; retained for accounting. Fixed version starts new runs.",
            },
        )
        engine.release(r["_id"])
    completed = [r for r in existing if r["status"] == "completed"]
    remaining = 10 - sum(r["spent_usd"] for r in existing)
    per_run_cap = min(4, remaining / max(1, 2 - len(completed)))
    for index in range(len(completed), 2):
        c = template_config("sensor")
        c["object"] = {"slug": "smoke-sensor", "name": "Package sensor smoke test"}
        c["run"].update(iterations=1, budget_usd=per_run_cap, mode="live" if args.live else "replay")
        c["task"]["description"] = (
            "Reduce sensor mount mass while preserving interfaces and all fixed stiffness and stress checks. Make a conservative, buildable change."
        )
        if index:
            detail = engine.detail("smoke-sensor")
            best = detail["runs"][0]["best_id"]
            if not best:
                raise RuntimeError("No passing seed available for continuation")
            c["continuation"] = {"seed_candidate_id": best}
        run = engine.start(yaml.safe_dump(c, sort_keys=False))
        print(json.dumps({"run_id": run["_id"], "stage": "started", "mode": c["run"]["mode"]}), flush=True)
        try:
            engine.execute(run["_id"])
        except Exception as exc:
            engine.store.update("runs", run["_id"], {"status": "paused", "error": type(exc).__name__})
            raise
        finally:
            engine.release(run["_id"])
        print(
            json.dumps(
                {
                    "run_id": run["_id"],
                    "status": engine.store.get("runs", run["_id"])["status"],
                    "spent_usd": engine.store.get("runs", run["_id"])["spent_usd"],
                }
            ),
            flush=True,
        )
    detail = engine.detail("smoke-sensor")
    report = {
        "mode": "live" if args.live else "replay",
        "storage": engine.store.backend,
        "runs": [
            {
                "id": r["_id"],
                "status": r["status"],
                "parent_run_id": r["parent_run_id"],
                "best_id": r["best_id"],
                "spent_usd": r["spent_usd"],
            }
            for r in detail["runs"]
        ],
        "designs": [
            {"id": d["_id"], "outcome": d["evaluation"]["outcome"], "metrics": d["evaluation"]["metrics"]}
            for d in detail["designs"]
        ],
        "tools": len(engine.store.list("tools")),
        "tool_uses": len(engine.store.list("tool_uses")),
    }
    (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "report": str(root / "report.json"),
                "spent_usd": sum(r["spent_usd"] for r in report["runs"]),
                "designs": len(report["designs"]),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
