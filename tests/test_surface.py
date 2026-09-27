import copy
import os

import pytest

from sandbox.surface_geometry import SHAPE_BOUNDS, stations, validate
from sandbox.vtol_family import BASELINE


def fixture():
    section = dict(
        upper_weights=[0.2] * 8, lower_weights=[-0.15] * 8, leading_edge_weight=0, TE_thickness=0.001
    )
    return dict(
        version=1,
        dimensions=copy.deepcopy(BASELINE),
        root=section,
        tip=copy.deepcopy(section),
        shape={k: 0 if k == "mid_twist_offset" else 1 for k in SHAPE_BOUNDS},
    )


def test_nested_geometry_rejects_nonfinite_and_unknown_fields():
    g = fixture()
    validate(g)
    for modify in [
        lambda s: s["root"]["upper_weights"].__setitem__(0, float("nan")),
        lambda s: s["shape"].__setitem__("mid_chord_factor", 2),
        lambda s: s["dimensions"].__setitem__("battery_wh", 1000),
        lambda s: s["tip"].__setitem__("TE_thickness", -1),
    ]:
        bad = copy.deepcopy(g)
        modify(bad)
        with pytest.raises(ValueError):
            validate(bad)


def test_middle_chord_keeps_quarter_chord_line():
    g = fixture()
    old = stations(g)[1]
    g["shape"]["mid_chord_factor"] = 1.08
    new = stations(g)[1]
    assert old["x"] + 0.25 * old["chord"] == pytest.approx(new["x"] + 0.25 * new["chord"])
    assert new["chord"] > old["chord"]


def test_control_tool_contract_and_budget_reservations(tmp_path):
    from davinci.budget import Budget, BudgetExceeded
    from davinci.store import Store
    from scripts.surface_study import definitions

    assert {t["name"] for t in definitions("control")} == {"edit_geometry", "submit_design"}
    assert "optimize_sections" in {t["name"] for t in definitions("surface_tools")}
    store = Store(tmp_path)
    store.insert("runs", {"_id": "arm", "spent_usd": 0, "budget_usd": 27, "revision": 0})
    budget = Budget(store, 60)
    held = budget.reserve("arm", 26)
    with pytest.raises(BudgetExceeded):
        budget.reserve("arm", 2)
    budget.settle(held, 26)
    with pytest.raises(BudgetExceeded):
        budget.reserve("arm", 2)
    assert store.get("runs", "arm")["spent_usd"] == 26


def test_cache_and_arm_memory_identities(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    import scripts.surface_study as module
    from davinci.models import digest

    study = module.Study.__new__(module.Study)
    study.root = tmp_path
    study.version = "v"
    study.image = "image"
    study.runner = None
    monkeypatch.setattr(module, "evaluator_version", lambda: "v")
    monkeypatch.setattr(module, "image_digest", lambda: "image")
    calls = []
    monkeypatch.setattr(
        module, "evaluate", lambda *args: (calls.append(args) or {"outcome": "passed", "metrics": {}}, {})
    )
    geometry = fixture()
    folder = tmp_path / "evaluate-6"
    folder.mkdir()
    prepared = {
        "outcome": "passed",
        "metrics": {"range_km": {"value": 42}},
        "execution": {
            "geometry_digest": digest(geometry),
            "evaluator_version": "v",
            "image_digest": "image",
            "resolution": 6,
            "nonlinear": False,
        },
    }
    (folder / "result.json").write_text(json.dumps(prepared))
    assert study.cached_evaluation(geometry)[0]["metrics"]["range_km"]["value"] == 42
    assert not calls
    study.cached_evaluation(geometry, 8)
    assert len(calls) == 1
    monkeypatch.setattr(module, "evaluator_version", lambda: "changed")
    with pytest.raises(ValueError, match="Frozen"):
        study.cached_evaluation(geometry)
    pipelines = []
    study.store = SimpleNamespace(
        db=SimpleNamespace(memories=SimpleNamespace(aggregate=lambda p: pipelines.append(p) or []))
    )
    provider = SimpleNamespace(embed=lambda *args: [0.0])
    study.recall("control", provider)
    study.recall("surface_tools", provider)
    filters = [p[0]["$vectorSearch"]["filter"]["specification_id"] for p in pipelines]
    assert filters == [module.STUDY + "-control", module.STUDY + "-surface_tools"]


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires CAD container")
def test_surface_section_sensitivity_and_smooth_step(tmp_path):
    from davinci.config import Settings
    from davinci.runner import Runner
    from davinci.surface import tool

    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    g, _ = tool(runner, "seed", {"parameters": BASELINE})
    spec = g["geometry"]
    conditions = [{"reynolds": 300000, "alpha_deg": 4}]
    before, _ = tool(runner, "analyze", {"geometry": spec, "conditions": conditions})
    after, _ = tool(
        runner,
        "edit",
        {"geometry": spec, "edits": {"camber_scale": 1.2, "shape": {"mid_chord_factor": 1.02}}},
    )
    aero, _ = tool(runner, "analyze", {"geometry": after["geometry"], "conditions": conditions})
    assert aero["sections"][0]["CL"] > before["sections"][0]["CL"]
    assert aero["sections"][0]["CM"] != before["sections"][0]["CM"]
    preview, files = tool(runner, "preview", {"geometry": after["geometry"]})
    assert preview["valid_solids"] > 15
    assert files["model.glb"][:4] == b"glTF"
    assert b"ISO-10303-21" in files["model.step"]
    with pytest.raises(RuntimeError):
        tool(runner, "edit", {"geometry": spec, "edits": {"thickness_scale": 0.1}})


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires CAD container")
def test_constrained_section_optimizer_returns_supported_new_geometry(tmp_path):
    from davinci.config import Settings
    from davinci.runner import Runner
    from davinci.surface import tool

    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    original, _ = tool(runner, "seed", {"parameters": BASELINE})
    result, _ = tool(
        runner,
        "optimize",
        {
            "geometry": original["geometry"],
            "targets": {"reynolds": 300000, "lift_coefficient": 0.6, "min_thickness": 0.12},
        },
    )
    validate(result["geometry"])
    assert result["geometry"]["root"] != original["geometry"]["root"]
    assert result["min_confidence"] >= 0.95
    assert result["seconds"] < 180
    assert result["numerical_evaluations"] > 1


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires CAD container")
def test_newton_flow_agrees_with_original_nonlinear_solver(tmp_path):
    from davinci.config import Settings
    from davinci.runner import Runner
    from davinci.surface import IMAGE, inputs

    source = """import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
from surface_geometry import seed
from surface_physics import solve
from vtol_family import BASELINE
g=seed(BASELINE)
fast=solve(g,.4,15,4,-2,4,nonlinear=True)
reference=solve(g,.4,15,4,-2,4,nonlinear=True,details=True)
for key in ('CL','CD','Cm','Cn'):
 assert abs(fast[key]-reference[key])<1e-6,(key,fast[key],reference[key])
assert reference['min_confidence']>.9
"""
    Runner(Settings(_env_file=None, davinci_data_dir=tmp_path)).execute(
        "/input/check.py", inputs() | {"check.py": source}, timeout=180, image=IMAGE
    )
