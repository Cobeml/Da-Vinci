import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml
from fastapi.testclient import TestClient

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.cli import initialize
from davinci.product.config import parse_yaml
from davinci.product.engine import Engine
from davinci.product.tasks import score_evaluation, snapshot, template_config


@pytest.fixture
def engine(tmp_path):
    return Engine(tmp_path, credentials=Settings(_env_file=None))


def config(name="sensor"):
    c = template_config(name)
    c["run"].update(mode="replay", iterations=1)
    return yaml.safe_dump(c)


def start(engine, content=None):
    content = content or config()
    c, t = engine.validate(content)
    return engine.create_run(c, t, content, "sha256:test")


def test_yaml_rejects_duplicates_units_unknown_fields(engine):
    with pytest.raises(ValueError):
        parse_yaml("version: 1\nversion: 2")
    c = template_config("sensor")
    c["constraints"] = [dict(metric="mass_g", operator="<=", value=3, unit="kg")]
    with pytest.raises(ValueError, match="wrong unit"):
        engine.validate(yaml.safe_dump(c))
    c = template_config("sensor")
    c["run"]["hidden"] = True
    with pytest.raises(ValueError):
        engine.validate(yaml.safe_dump(c))
    c = template_config("sensor")
    c["objective"]["target"] = float("nan")
    with pytest.raises(ValueError):
        engine.validate(yaml.safe_dump(c))


def test_custom_snapshot_path_and_resource_freezing(tmp_path):
    initialize(tmp_path / "custom", "custom")
    root = tmp_path / "custom"
    c = parse_yaml((root / "run.yaml").read_text())
    a = snapshot(c, root)
    (root / "task" / "evaluate.py").write_text("# changed\n" + (root / "task" / "evaluate.py").read_text())
    assert snapshot(c, root)["version"] != a["version"]
    c.task.path = "../outside"
    with pytest.raises(ValueError, match="inside"):
        snapshot(c, root)


def test_compare_and_set_only_one_start(engine):
    def attempt(_):
        try:
            return start(engine)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=3) as pool:
        runs = list(pool.map(attempt, range(3)))
    assert sum(r is not None for r in runs) == 1


def test_missing_metrics_never_win(engine):
    c, t = engine.validate(config())
    e = score_evaluation(t, c, {"outcome": "passed", "metrics": {}, "violations": []})
    assert e["outcome"] == "failed"
    with pytest.raises(ValueError):
        score_evaluation(
            t,
            c,
            {
                "outcome": "passed",
                "metrics": {"mass_g": {"value": float("nan"), "unit": "g"}},
                "violations": [],
            },
        )


def fake_evaluate(runner, task, p, source, image):
    return {
        "outcome": "passed",
        "metrics": {
            "mass_g": {"value": p["wall_mm"] * 10, "unit": "g"},
            "deflection_mm": {"value": 0.1, "unit": "mm"},
        },
        "violations": [],
    }, {"model.step": b"step", "model.glb": b"glb"}


def fake_execute(entry, files, **kw):
    return {"result.json": json.dumps({"passed": True, "delta_percent": 0}).encode()}, "", 0


def test_iterations_continuation_tools_and_restart(engine, monkeypatch):
    monkeypatch.setattr("davinci.product.engine.evaluate", fake_evaluate)
    monkeypatch.setattr(engine.runner, "execute", fake_execute)
    run = start(engine)
    engine.execute(run["_id"])
    engine.release(run["_id"])
    detail = engine.detail("my-sensor")
    assert detail["runs"][0]["status"] == "completed"
    assert len(detail["designs"]) == 2
    assert detail["runs"][0]["best_id"].endswith("001")
    assert len(engine.store.list("tools")) == 1
    assert len(engine.store.list("tool_uses")) == 2
    c = template_config("sensor")
    c["run"].update(mode="replay", iterations=1)
    c["continuation"] = {"seed_candidate_id": detail["runs"][0]["best_id"]}
    new = start(engine, yaml.safe_dump(c))
    assert new["parent_run_id"] == run["_id"]
    assert new["seed_parameters"]["wall_mm"] == 4
    engine.recover()
    assert engine.store.get("runs", new["_id"])["status"] == "paused"
    engine.resume(new["_id"])
    engine.execute(new["_id"])
    assert len(engine.store.list("tools")) == 1  # reuse across compatible runs
    assert len(engine.store.list("candidates")) == 4
    # No duplicate candidates, evaluations, tools or requests on repeated checkpoint execution.
    engine.store.update("runs", new["_id"], {"status": "running"})
    engine.execute(new["_id"])
    assert len(engine.store.list("evaluations")) == 4


def test_recovery_wont_repeat_uncertain_requests(engine):
    run = start(engine)
    engine.store.insert("requests", {"_id": "uncertain", "run_id": run["_id"], "status": "pending"})
    engine.recover()
    with pytest.raises(ValueError, match="uncertain"):
        engine.resume(run["_id"])


def test_api_boundary_and_validation(engine):
    client = TestClient(create_app(engine.workspace, engine=engine, run_worker=False))
    assert client.get("/api/v1/tasks").status_code == 200
    assert client.get("/api/v1/health").json()["storage"] == "sqlite-local"
    assert client.post("/api/v1/validate", json={"yaml": config()}).status_code == 200
    assert (
        client.post(
            "/api/v1/validate", json={"yaml": config()}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/health", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/v1/objects/missing").status_code == 404
    assert "openai_api_key" not in client.get("/api/v1/health").text


def test_incompatible_object_continuation_rejected(engine, monkeypatch):
    monkeypatch.setattr("davinci.product.engine.evaluate", fake_evaluate)
    monkeypatch.setattr(engine.runner, "execute", fake_execute)
    r = start(engine)
    engine.execute(r["_id"])
    engine.release(r["_id"])
    c = template_config("sensor")
    c["run"]["mode"] = "replay"
    c["object"]["slug"] = "other"
    c["continuation"] = {"seed_candidate_id": r["_id"] + "-000"}
    with pytest.raises(ValueError, match="this object"):
        start(engine, yaml.safe_dump(c))
