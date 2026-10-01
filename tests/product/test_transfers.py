"""Ownership/continuation and read-only UI parity, using deterministic solver fixtures."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from test_lifecycle import candidate, cmd, frozen
from test_managed import drive, engine_at, request

from davinci.product.api import create_app
from davinci.product.lifecycle import Conflict
from davinci.product.transfers import continuation, handoff


def transfer_body(row, driver="external", actor="coding-agent"):
    return {
        **cmd(row, "handoff").model_dump(),
        "driver": driver,
        "new_actor": actor,
        "reason": "Explicit user handoff",
    }


def test_handoff_fences_old_owner_and_preserves_suite(tmp_path):
    engine = engine_at(tmp_path)
    row = drive(
        engine, engine.managed.workflow.start(request())["_id"], lambda r: r["managed"]["stage"] == "propose"
    )
    suite = row["suite_id"]
    before = row
    body = transfer_body(row)
    row = handoff(engine, row["_id"], body)
    assert row["suite_id"] == suite and row["driver"] == "external"
    assert row["managed"]["status"] == "handed_off"
    assert handoff(engine, row["_id"], body) == row
    with pytest.raises(Conflict):
        engine.lifecycle.submit_candidate(row["_id"], cmd(before, "old-owner"), candidate())
    count = len(engine.model_calls)
    engine.managed.workflow.tick(row["_id"])
    assert len(engine.model_calls) == count
    with pytest.raises(Conflict):
        handoff(engine, row["_id"], {**body, "reason": "Changed payload"})
    row = engine.lifecycle.submit_candidate(row["_id"], cmd(row, "external-design"), candidate())
    engine.lifecycle.schedule(row["_id"], cmd(row, "eval"), "evaluate")
    queued = engine.lifecycle.get(row["_id"])
    with pytest.raises(Conflict):
        handoff(engine, row["_id"], transfer_body(queued, "managed", "user"))
    engine.lifecycle.execute_scheduled(row["_id"])
    row = engine.lifecycle.get(row["_id"])
    row = handoff(engine, row["_id"], {**transfer_body(row, "managed", "user"), "operation_id": "back"})
    row = drive(engine, row["_id"])
    assert row["phase"] == "completed" and row["suite_id"] == suite
    assert row["report"]["accepted_candidate_ids"]


def test_continuation_does_not_copy_passes_or_change_suite(tmp_path):
    engine = engine_at(tmp_path)
    old = drive(engine, engine.managed.workflow.start(request())["_id"])
    payload = {
        **cmd(old, "continue").model_dump(),
        "driver": "external",
        "new_actor": "coder",
        "candidate_id": old["candidates"][-1]["id"],
    }
    child = continuation(engine, old["_id"], payload)
    assert child["suite_id"] == old["suite_id"] and not child["results"]
    assert child["phase"] == "candidate_submitted" and child["continuation"]["results_inherited"] is False
    assert continuation(engine, old["_id"], payload)["_id"] == child["_id"]
    assert engine.lifecycle.get(old["_id"])["report"] == old["report"]
    engine.lifecycle.schedule(child["_id"], cmd(child, "eval"), "evaluate")
    engine.lifecycle.execute_scheduled(child["_id"])
    child = engine.lifecycle.get(child["_id"])
    child = engine.lifecycle.reflect(
        child["_id"], cmd(child, "reflect"), lesson="Fresh evidence, no inherited score"
    )
    child = engine.lifecycle.finalize(child["_id"], cmd(child, "finalize"))
    assert child["report"]["accepted_candidate_ids"]
    more = continuation(
        engine,
        child["_id"],
        {
            **cmd(child, "managed-cont").model_dump(),
            "driver": "managed",
            "new_actor": "user",
            "candidate_id": child["candidates"][0]["id"],
            "policy": {"max_candidates": 2, "min_candidates": 2},
        },
    )
    assert not more["results"]
    assert drive(engine, more["_id"])["report"]["accepted_candidate_ids"]


def test_atomic_racing_owner_changes(tmp_path):
    engine = engine_at(tmp_path)
    row = frozen(engine)

    def transfer(index):
        try:
            return handoff(
                engine,
                row["_id"],
                {**transfer_body(row, actor=f"new-{index}"), "operation_id": f"transfer-{index}"},
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(transfer, range(2)))
    assert sum(r is not None for r in results) == 1
    assert len(engine.lifecycle.get(row["_id"])["handoffs"]) == 1


def test_both_drivers_visible_and_no_credential_leak(tmp_path):
    engine = engine_at(tmp_path)
    engine.credentials.openai_api_key = "secret-fixture-never-export"
    managed = drive(engine, engine.managed.workflow.start(request())["_id"])
    external = engine.lifecycle.open(
        {
            "object": {"slug": "external", "name": "External"},
            "description": "External task",
            "actor": "coder",
            "operation_id": "external",
        }
    )
    with TestClient(create_app(tmp_path, engine=engine, run_worker=False)) as client:
        cards = client.get("/api/v2/workspace/objects").json()
        assert {x["_id"] for x in cards} == {"beam", "external"}
        assert not cards[0].get("validated")
        detail = client.get("/api/v2/workspace/objects/beam").json()
        view = detail["runs"][0]["experiment"]
        assert view["report"]["accepted_candidate_ids"]
        assert "provider_settings" not in view
        routes = [
            "/api/v2/workspace/connection",
            "/api/v2/workspace/objects",
            "/api/v2/workspace/objects/beam",
            f"/api/v2/experiments/{managed['_id']}/report",
            f"/api/v2/experiments/{external['_id']}",
        ]
        for route in routes:
            assert engine.credentials.openai_api_key not in client.get(route).text
        projection = client.get("/api/v2/workspace/objects/external").json()["runs"][0]["experiment"]
        assert projection["next_actions"] and not projection["results"]
        assert not engine.store.list("requests")
        assert engine.credentials.openai_api_key not in json.dumps(managed)


def test_required_native_gate_missing_image_is_failure(monkeypatch):
    import subprocess

    from scripts.required_native import main

    def missing(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "docker")

    monkeypatch.setattr("scripts.required_native.subprocess.run", missing)
    with pytest.raises(SystemExit, match="Required solver image unavailable"):
        main()
