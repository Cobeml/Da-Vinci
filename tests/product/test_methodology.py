"""Orchestration checks only. Native evidence comes from the separate benchmark."""

import copy
import sys

import pytest
from test_experience import engine, note, open_run

from davinci.product import recipes
from davinci.product.contracts import OpenExperiment
from davinci.product.live_methodology import independent_check
from davinci.product.methodology import requirements


@pytest.mark.parametrize("driver", ["external", "managed"])
def test_frozen_retrieval_corpus_and_disable(tmp_path, driver):
    e = engine(tmp_path, embedding=True)
    library = open_run(e, "library", driver)
    reusable = note(e, library, op="reusable")
    note(e, library, op="answer", claim="Cantilever deflection task-specific answer must not leak")
    for mode in ("enabled", "disabled"):
        row = e.lifecycle.open(
            OpenExperiment(
                object={"slug": mode, "name": mode},
                description="cantilever deflection",
                actor="agent",
                operation_id=mode,
                driver=driver,
                metadata={"memory_retrieval": mode, "memory_record_ids": [reusable["id"]]},
            )
        )
        results = e.lifecycle.retrieve("cantilever deflection", experiment_id=row["_id"])
        direct = e.experience.search({"query": "cantilever deflection", "experiment_id": row["_id"]})
        assert {r["id"] for r in direct["items"]} == {r["id"] for r in results}
        assert {r["id"] for r in results} == ({reusable["id"]} if mode == "enabled" else set())
    # A known experiment identity cannot bypass project isolation.
    e.experience.scope["project_id"] = "foreign"
    with pytest.raises(KeyError):
        e.lifecycle.get(library["_id"])


def test_live_protocol_requires_opt_in_before_connecting(monkeypatch, tmp_path):
    from davinci.product import live_methodology as live

    monkeypatch.setenv("OPENAI_API_KEY", "ambient-key-must-not-be-used")
    monkeypatch.setattr(live, "Client", lambda *a: pytest.fail("Must not connect without opt-in"))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "live",
            "--workspace",
            str(tmp_path),
            "--output",
            str(tmp_path),
            "--budget-usd",
            "1",
            "--operation",
            "test",
        ],
    )
    with pytest.raises(SystemExit) as exc:
        live.main()
    assert exc.value.code == 2


def test_live_independent_contract_rejects_relaxed_limits():
    plan = recipes.make_plan(requirements("heldout-a")).model_dump(mode="json")
    row = {"plan": plan, "results": [], "managed": {}}
    assert independent_check(row)["contract_mismatches"] == []
    assert not independent_check(row)["protocol_accepted"]
    changed = copy.deepcopy(row)
    changed["plan"]["tests"][0]["criteria"][0]["limit"] *= 100
    assert "tests" in independent_check(changed)["contract_mismatches"]
