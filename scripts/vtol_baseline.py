"""Local baseline feasibility probe: no model or database calls."""

import json
from pathlib import Path

from davinci.config import Settings
from davinci.runner import Runner
from davinci.vtol import REFERENCE_SOURCE, evaluate
from sandbox.vtol_family import BASELINE

if __name__ == "__main__":
    runner = Runner(Settings(_env_file=None))
    result, outputs = evaluate(runner, REFERENCE_SOURCE, BASELINE)
    root = Path("runtime/vtol-baseline")
    root.mkdir(exist_ok=True)
    (root / "result.json").write_text(json.dumps(result, indent=2))
    for name, value in outputs.items():
        (root / name).write_bytes(value)
    print(
        json.dumps(
            {
                "outcome": result["outcome"],
                "metrics": result["metrics"],
                "violations": result["violations"],
                "structure": result["performance"]["nominal"]["structure"],
                "components": result["components"],
            },
            indent=2,
        )
    )
