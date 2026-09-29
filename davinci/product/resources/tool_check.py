"""Trusted objective-delta fixtures, executed separately from the generated tool."""

import json
import math
from pathlib import Path

from tool import run

checks = []
for baseline, current, direction, expected in [
    (100, 80, "minimize", 20),
    (80, 100, "maximize", 25),
    (-10, -5, "maximize", 50),
    (4, 4, "minimize", 0),
]:
    actual = run(dict(baseline=baseline, current=current, direction=direction))["delta_percent"]
    assert math.isfinite(actual) and math.isclose(actual, expected, abs_tol=1e-8)
    checks.append({"expected": expected, "actual": actual})
for args in [
    {},
    {"baseline": 0, "current": 1, "direction": "minimize"},
    {"baseline": 1, "current": float("nan"), "direction": "minimize"},
    {"baseline": 1, "current": 2, "direction": "sideways"},
]:
    try:
        run(args)
    except (ValueError, KeyError, TypeError):
        pass
    else:
        raise AssertionError("Invalid input accepted")
Path("/output/result.json").write_text(json.dumps({"passed": True, "checks": checks}))
