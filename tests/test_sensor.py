"""Independent checks for the richer geometry family; no live services or credentials."""

import os

import pytest

from davinci.config import Settings
from davinci.runner import Runner
from davinci.sensor import REFERENCE_SOURCE, evaluate

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires Docker CAD")]


def test_cradle_lightweighting_and_failure(tmp_path):
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    baseline = {"base_mm": 6, "wall_mm": 6, "window_mm": 0, "window_style": 0, "base_slots": 0, "gusset_mm": 0}
    reference, _ = evaluate(runner, REFERENCE_SOURCE, baseline)
    lighter = {**baseline, "base_mm": 2.5, "wall_mm": 4, "window_mm": 40, "window_style": 2, "base_slots": 2}
    result, artifacts = evaluate(runner, REFERENCE_SOURCE, lighter)
    assert reference["outcome"] == result["outcome"] == "passed"
    assert result["metrics"]["mass_g"]["value"] < reference["metrics"]["mass_g"]["value"] * .65
    assert artifacts["model.glb"][:4] == b"glTF"
    failed, _ = evaluate(runner, REFERENCE_SOURCE, {**lighter, "wall_mm": 2, "window_mm": 66})
    assert failed["outcome"] == "failed"
    assert "DEFLECTION_LIMIT" in [v["code"] for v in failed["violations"]]


def test_cradle_rejects_unsupported_geometry(tmp_path):
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    parameters = {"base_mm": 3, "wall_mm": 4, "window_mm": 40, "window_style": 1, "base_slots": 1, "gusset_mm": 8}
    changed = REFERENCE_SOURCE.replace("build_cradle(parameters)",
                                       "build_cradle(parameters).cut(cq.Workplane('XY').box(30, 90, 90))")
    result, _ = evaluate(runner, changed, parameters)
    assert "UNSUPPORTED_GEOMETRY" in [v["code"] for v in result["violations"]]
