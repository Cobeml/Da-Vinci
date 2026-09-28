"""Local surface-tool preparation; no API calls or database writes."""

import argparse
import json
from pathlib import Path

from davinci.config import Settings
from davinci.runner import Runner
from davinci.surface import crosscheck, evaluate, evaluator_version, tool


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["seed", "preview", "evaluate", "optimize", "probe", "inspect", "crosscheck"]
    )
    parser.add_argument("--nonlinear", action="store_true")
    parser.add_argument("--resolution", type=int, default=6)
    parser.add_argument("--geometry", default="runtime/survey-vtol-cst-v1/seed.json")
    args = parser.parse_args()
    settings = Settings(_env_file=None)
    runner = Runner(settings)
    root = settings.root / "survey-vtol-cst-v1"
    root.mkdir(exist_ok=True)
    if args.action == "seed":
        old = json.loads(Path("web/data/vtol-gallery.json").read_text())
        p = next(d["parameters"] for d in old["designs"] if d["_id"] == old["best_id"])
        # Give the same enclosed shell and payload clearance to both experimental arms.
        p = {
            **p,
            "wing_x": 0.30,
            "fuselage_width": 0.17,
            "fuselage_height": 0.18,
            "nose_fraction": 0.28,
            "tail_fraction": 0.76,
        }
        r, _ = tool(runner, "seed", {"parameters": p})
        (root / "seed.json").write_text(json.dumps(r["geometry"], indent=2))
        print("Saved common seed; no API calls")
        return
    geometry = json.loads(Path(args.geometry).read_text())
    if args.action == "evaluate":
        r, files = evaluate(runner, geometry, args.resolution, args.nonlinear)
    elif args.action == "crosscheck":
        source = "evaluate" + ("-nonlinear" if args.nonlinear else "") + "-" + str(args.resolution)
        evaluation = json.loads((root / source / "result.json").read_text())
        r = crosscheck(runner, geometry, evaluation["performance"]["direct_audit"])
        files = {}
    else:
        r, files = tool(runner, args.action, {"geometry": geometry, "cg": 0.397})
    key = args.action + ("-nonlinear" if args.nonlinear else "") + "-" + str(args.resolution)
    folder = root / key
    folder.mkdir(exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    (folder / "result.json").write_text(json.dumps(r, indent=2))
    print(
        json.dumps(
            {
                "version": evaluator_version(),
                "result": {k: v for k, v in r.items() if k not in ("geometry", "performance", "components")},
            }
        )
    )


if __name__ == "__main__":
    main()
