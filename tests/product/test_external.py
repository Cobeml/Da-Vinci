"""External HTTP/CLI integration with a provider that must never be constructed."""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from test_lifecycle import EVALUATOR, IMAGE, FixtureRunner, candidate, plan, values

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.cli import initialize
from davinci.product.engine import Engine
from davinci.product.protocol import build_catalog, schema_catalog


class ForbiddenProvider:
    def __init__(self, *args, **kwargs):
        raise AssertionError("External route constructed a provider")

    def request(self, *args, **kwargs):
        raise AssertionError("External generation call")

    def embed(self, *args, **kwargs):
        raise AssertionError("External embedding call")


@pytest.fixture(params=["", "present-but-must-not-be-used"])
def external(tmp_path, monkeypatch, request):
    monkeypatch.setenv("OPENAI_API_KEY", request.param)
    monkeypatch.delenv("MONGODB_URI", raising=False)
    engine = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, mongodb_uri=""),
        provider=ForbiddenProvider,
        runner=FixtureRunner(),
    )
    # Even an explicit embedding preference does not activate an external provider.
    engine.options.embeddings = True
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        yield client, engine


def open_experiment(client, operation="open"):
    response = client.post(
        "/api/v2/experiments",
        json={
            "object": {"slug": "beam", "name": "Beam"},
            "description": "Reduce beam mass under a fixed 100 N tip load",
            "driver": "external",
            "mode": "live",
            "actor": "coding-agent",
            "operation_id": operation,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def mutate(client, eid, action, operation, payload=None):
    row = client.get("/api/v2/experiments/" + eid).json()
    body = {"actor": row["actor"], "revision": row["revision"], "operation_id": operation, **(payload or {})}
    response = client.post(f"/api/v2/experiments/{eid}/{action}", json=body)
    assert response.status_code in (200, 202), response.text
    return response.json()


def wait(client, eid, job):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        response = client.get(f"/api/v2/experiments/{eid}/jobs/{job['id']}")
        assert response.status_code == 200, response.text
        data = response.json()
        if data["status"] not in ("running", "queued"):
            assert data["status"] == "completed", data
            return data
        time.sleep(0.01)
    pytest.fail("Job did not finish")


def prepare(client, row):
    eid = row["_id"]
    mutate(
        client,
        eid,
        "plan",
        "plan",
        {
            "plan": plan().model_dump(),
            "evaluator": {"resources": {"evaluate.py": EVALUATOR}, "provenance": "fixture"},
            "runtime": {"image": IMAGE, "solver": "fixture", "provenance": "fixture"},
        },
    )
    for t in (4, 2):
        job = mutate(
            client,
            eid,
            "reference-builds",
            f"reference-{t}",
            {"reference": {"candidate": candidate(t).model_dump(), "provenance": "fixture"}},
        )
        fixture = wait(client, eid, job)["fixture_artifacts"][0]
        job = mutate(
            client,
            eid,
            "verify",
            f"verify-{t}",
            {
                "verification": {
                    "test_id": "beam",
                    "fixture_artifact": fixture,
                    "expected_status": "pass" if t == 4 else "physical_failure",
                    "reference_metrics": {
                        k: {"value": v, "unit": plan().tests[0].metrics[k], "dimension": "reference"}
                        for k, v in values(t).items()
                    },
                    "tolerances": {k: 0.0001 for k in values(t)},
                    "provenance": "closed form",
                }
            },
        )
        wait(client, eid, job)
    assert client.get(f"/api/v2/experiments/{eid}/plan-validation").json()["ready_to_freeze"]
    return mutate(client, eid, "freeze", "freeze")


def test_full_external_route_provider_isolation_and_idempotency(external):
    client, engine = external
    row = open_experiment(client)
    eid = row["_id"]
    assert open_experiment(client)["_id"] == eid
    bad = {**row["opening"], "description": "Changed request"}
    assert client.post("/api/v2/experiments", json=bad).status_code == 409
    row = prepare(client, row)
    suite = row["suite_id"]
    for index, thickness in enumerate((2, 4)):
        row = mutate(
            client, eid, "candidates", f"candidate-{index}", {"candidate": candidate(thickness).model_dump()}
        )
        assert row["suite_id"] == suite
        job = mutate(client, eid, "evaluate", f"evaluate-{index}")
        assert job["status"] in ("queued", "running")
        assert mutate(client, eid, "evaluate", f"evaluate-{index}")["id"] == job["id"]
        done = wait(client, eid, job)
        result = client.get(f"/api/v2/experiments/{eid}/results").json()["results"][-1]
        assert result["design_accepted"] is (thickness == 4)
        assert result["id"] in done["result_ids"]
        step = client.get("/api/v1/artifacts/" + result["artifacts"]["model.step"])
        assert step.status_code == 200
        row = mutate(
            client,
            eid,
            "reflections",
            f"reflect-{index}",
            {"lesson": "Thicker might help", "result_id": result["id"]},
        )
        assert row["experiences"][-1]["support"] == "hypothesis"
    mutate(client, eid, "finalize", "finalize")
    exported = client.get(f"/api/v2/experiments/{eid}/report").json()
    assert len(exported["report"]["accepted_candidate_ids"]) == 1
    assert len(exported["experiment"]["jobs"]) == 6
    assert not engine.store.list("requests")
    assert client.get("/api/v2/experience?q=thicker").json()[0]["transfers_acceptance"] is False
    # External experiments never enter the proposal/reflection loop.
    body = {"actor": row["actor"], "revision": row["revision"], "operation_id": "managed"}
    assert client.post(f"/api/v2/experiments/{eid}/managed/propose", json=body).status_code == 409


def test_reject_trusted_scores_and_frozen_changes(external):
    client, _ = external
    row = prepare(client, open_experiment(client))
    eid = row["_id"]
    command = {"actor": row["actor"], "revision": row["revision"], "operation_id": "tamper"}
    assert (
        client.post(
            f"/api/v2/experiments/{eid}/plan", json={**command, "plan": plan().model_dump()}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v2/experiments/{eid}/evaluate", json={**command, "results": {"status": "pass"}}
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v2/experiments/{eid}/candidates",
            json={**command, "candidate": {**candidate().model_dump(), "accepted": True}},
        ).status_code
        == 422
    )
    assert client.post(f"/api/v2/experiments/{eid}/results", json={"status": "pass"}).status_code == 405


def test_nonblocking_cancel_resume_and_old_jobs(external):
    client, engine = external
    row = prepare(client, open_experiment(client))
    eid = row["_id"]
    mutate(client, eid, "candidates", "candidate", {"candidate": candidate().model_dump()})
    entered, released = threading.Event(), threading.Event()
    original = engine.runner.execute

    def block(entry, files, **kwargs):
        entered.set()
        released.wait(10)
        return original(entry, files, **kwargs)

    engine.runner.execute = block
    job = mutate(client, eid, "evaluate", "slow")
    assert entered.wait(3)
    assert client.get(f"/api/v2/experiments/{eid}").json()["phase"] == "evaluating"
    mutate(client, eid, "cancel", "cancel")
    released.set()
    for _ in range(300):
        current = client.get(f"/api/v2/experiments/{eid}/jobs/{job['id']}").json()
        if current["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert current["status"] == "cancelled"
    assert not client.get(f"/api/v2/experiments/{eid}/results").json()["results"][-1]["design_accepted"]
    mutate(client, eid, "resume", "resume")
    engine.runner.execute = original
    mutate(client, eid, "reflections", "reflect", {"lesson": "Cancelled, no physical conclusion"})
    mutate(client, eid, "candidates", "replacement", {"candidate": candidate().model_dump()})
    wait(client, eid, mutate(client, eid, "evaluate", "fresh"))
    assert client.get(f"/api/v2/experiments/{eid}/jobs/{job['id']}").json()["status"] == "cancelled"


def test_installed_schema_and_agent_instructions(tmp_path):
    assert schema_catalog() == build_catalog()
    initialize(tmp_path / "workspace", "custom", driver="external")
    assert (tmp_path / "workspace" / "task" / "task.json").exists()  # original custom route preserved
    assert (tmp_path / "workspace" / "AGENTS.md").is_file()
    assert (tmp_path / "workspace" / "external" / "schemas.json").is_file()


def test_queued_job_survives_restart_and_reused_payload_conflicts(tmp_path):
    engine = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        provider=ForbiddenProvider,
        runner=FixtureRunner(),
    )
    with TestClient(create_app(tmp_path, engine=engine, run_worker=False)) as client:
        row = open_experiment(client)
        eid = row["_id"]
        mutate(
            client,
            eid,
            "plan",
            "plan",
            {
                "plan": plan().model_dump(),
                "evaluator": {"resources": {"evaluate.py": EVALUATOR}, "provenance": "fixture"},
                "runtime": {"image": IMAGE, "solver": "fixture", "provenance": "fixture"},
            },
        )
        payload = {"reference": {"candidate": candidate(4).model_dump(), "provenance": "reference"}}
        job = mutate(client, eid, "reference-builds", "reference", payload)
        assert job["status"] == "queued"
        current = client.get(f"/api/v2/experiments/{eid}").json()
        payload["reference"]["candidate"]["parameters"]["thickness"] = 2
        conflict = client.post(
            f"/api/v2/experiments/{eid}/reference-builds",
            json={
                **payload,
                "actor": current["actor"],
                "revision": current["revision"],
                "operation_id": "reference",
            },
        )
        assert conflict.status_code == 409
    restored = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        provider=ForbiddenProvider,
        runner=FixtureRunner(),
    )
    with TestClient(create_app(tmp_path, engine=restored)) as client:
        assert wait(client, eid, job)["fixture_artifacts"]
        assert not restored.store.list("requests")


def test_cancel_queued_then_resume_does_not_implicitly_requeue(tmp_path):
    engine = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        provider=ForbiddenProvider,
        runner=FixtureRunner(),
    )
    with TestClient(create_app(tmp_path, engine=engine, run_worker=False)) as client:
        eid = open_experiment(client)["_id"]
        mutate(
            client,
            eid,
            "plan",
            "plan",
            {
                "plan": plan().model_dump(),
                "evaluator": {"resources": {"evaluate.py": EVALUATOR}, "provenance": "fixture"},
                "runtime": {"image": IMAGE, "solver": "fixture", "provenance": "fixture"},
            },
        )
        job = mutate(
            client,
            eid,
            "reference-builds",
            "reference",
            {"reference": {"candidate": candidate(4).model_dump(), "provenance": "reference"}},
        )
        mutate(client, eid, "cancel", "cancel")
        row = mutate(client, eid, "resume", "resume")
        assert row["phase"] == "draft"
        assert client.get(f"/api/v2/experiments/{eid}/jobs/{job['id']}").json()["status"] == "cancelled"
        replay = mutate(
            client,
            eid,
            "reference-builds",
            "reference",
            {"reference": {"candidate": candidate(4).model_dump(), "provenance": "reference"}},
        )
        assert replay["id"] == job["id"] and replay["status"] == "cancelled"


def test_external_queue_waits_for_managed_execution_owner(external, monkeypatch):
    import subprocess

    import yaml

    from davinci.product.tasks import template_config

    client, engine = external
    entered, released = threading.Event(), threading.Event()
    consumed = []

    def managed_execution(run_id):
        consumed.append(run_id)
        entered.set()
        released.wait(10)
        engine.store.update("runs", run_id, {"status": "completed", "phase": "completed"})

    # Instrument the old loop, not the external route. It may only receive the v1 ID.
    monkeypatch.setattr(engine, "execute", managed_execution)
    original = subprocess.check_output
    monkeypatch.setattr(
        subprocess,
        "check_output",
        lambda args, **kw: IMAGE if args[:3] == ["docker", "image", "inspect"] else original(args, **kw),
    )
    cfg = template_config("sensor")
    cfg["run"]["mode"] = "replay"
    legacy = client.post("/api/v1/runs", json={"yaml": yaml.safe_dump(cfg)})
    assert legacy.status_code == 201
    assert entered.wait(3)
    eid = open_experiment(client)["_id"]
    mutate(
        client,
        eid,
        "plan",
        "plan",
        {
            "plan": plan().model_dump(),
            "evaluator": {"resources": {"evaluate.py": EVALUATOR}, "provenance": "fixture"},
            "runtime": {"image": IMAGE, "solver": "fixture", "provenance": "fixture"},
        },
    )
    job = mutate(
        client,
        eid,
        "reference-builds",
        "reference",
        {"reference": {"candidate": candidate(4).model_dump(), "provenance": "reference"}},
    )
    assert client.get(f"/api/v2/experiments/{eid}/jobs/{job['id']}").json()["status"] == "queued"
    released.set()
    assert wait(client, eid, job)["fixture_artifacts"]
    assert consumed == [legacy.json()["id"]]
