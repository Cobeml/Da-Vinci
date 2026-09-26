import os

import pytest

from davinci.config import Settings
from davinci.engine import Engine
from davinci.models import SPECIFICATION, PatchProposal, RunRequest
from davinci.templates import MOUNT_SOURCE, WING_SOURCE

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("DAVINCI_INTEGRATION") != "1",
        reason="Set DAVINCI_INTEGRATION=1 for real Docker/CAD checks",
    ),
]


@pytest.fixture
def engine(tmp_path):
    return Engine(Settings(davinci_data_dir=tmp_path, _env_file=None))


def test_measured_mass_units_and_invalid_thickness(engine):
    result, artifacts, _ = engine.runner.evaluate(
        MOUNT_SOURCE, {"thickness_mm": 3}, "structural", SPECIFICATION
    )
    expected = (80 * 40 - 2 * 3.141592653589793 * 2**2) * 3 * 1e-9 * 2700
    assert result["outcome"] == "passed", result
    assert result["metrics"]["mass_kg"]["value"] == pytest.approx(expected, rel=1e-5)
    assert artifacts["model.glb"][:4] == b"glTF"
    failed, _, _ = engine.runner.evaluate(MOUNT_SOURCE, {"thickness_mm": 1.5}, "structural", SPECIFICATION)
    assert "MINIMUM_THICKNESS" in [v["code"] for v in failed["violations"]]


def test_wing_gap_and_screening(engine):
    for gap, outcome in [(0.2, "failed"), (2.0, "passed")]:
        result, _, _ = engine.runner.evaluate(
            WING_SOURCE,
            {"span_mm": 600, "hinge_gap_mm": gap, "flap_fraction": 0.25},
            "aerodynamic",
            SPECIFICATION,
        )
        assert result["outcome"] == outcome, result
        assert result["metrics"]["induced_drag_n"]["value"] > 0


def test_full_replay_and_tool_reuse_after_restart(engine):
    run = engine.start(RunRequest(rounds=3))
    for _ in range(40):
        engine.reconcile()
        job = engine.store.claim(seconds=600)
        if not job:
            break
        engine.execute_job(job)
        if engine.store.get("runs", run["_id"])["status"] != "running":
            break
    final = engine.store.get("runs", run["_id"])
    assert final["status"] == "completed", engine.store.list("events")
    assert len(engine.store.list("evaluations")) == 6
    assert len(engine.store.list("champions")) >= 1
    assert engine.improvements.active()["_id"] != "release-baseline"
    assert any(e["kind"] == "tool_invoked" for e in engine.store.list("events"))
    restarted = Engine(engine.settings)
    tool = restarted.store.list("tools", {"status": "active"})[0]
    assert (
        restarted.improvements.invoke_tool(tool["_id"], {"dimensions_m": [2, 3, 4], "direction": [0, 0, 1]})[
            "projected_area_m2"
        ]
        == 6
    )


def test_bad_patch_cannot_promote_and_rollback(engine):
    run = engine.start(RunRequest(rounds=1))
    bad = PatchProposal(summary="broken", files={"orchestrator.py": "raise RuntimeError('broken')"})
    release = engine.improvements.propose_release(bad, run["_id"], "fixture")
    assert release["status"] == "rejected"
    assert not engine.improvements.activate(release["_id"], run["_id"])
    assert engine.improvements.active()["_id"] == "release-baseline"
    with pytest.raises(ValueError):
        engine.improvements.propose_release(
            PatchProposal(summary="escape", files={"../../evaluate.py": "pass"}), run["_id"], "fixture"
        )
