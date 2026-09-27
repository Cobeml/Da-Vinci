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
