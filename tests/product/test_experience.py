"""Cross-task retrieval is not cross-task validation. All default providers are forbidden."""

import base64
import copy

import pytest
from fastapi.testclient import TestClient
from test_external import ForbiddenProvider
from test_lifecycle import FixtureRunner, cmd, evaluated, frozen

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.contracts import OpenExperiment
from davinci.product.engine import Engine
from davinci.product.lifecycle import Conflict
from davinci.product.memory_contracts import MemoryNote


def engine(root, project="default", embedding=False):
    root.mkdir(parents=True, exist_ok=True)
    (root / "workspace.yaml").write_text(
        "project_id: "
        + project
        + "\nembedding:\n  adapter: "
        + ("local-hash" if embedding else "disabled")
        + "\n"
    )
    return Engine(
        root,
        provider=ForbiddenProvider,
        runner=FixtureRunner(),
        credentials=Settings(_env_file=None, openai_api_key="unused-but-present", mongodb_uri=""),
    )


def open_run(e, name="mount", driver="external"):
    return e.lifecycle.open(
        OpenExperiment(
            object={"slug": name, "name": name},
            description="Reduce sensor mount beam deflection",
            actor="agent",
            operation_id="open-" + name,
            driver=driver,
        )
    )


def note(
    e, row, claim="Increase section depth to reduce cantilever deflection.", op="note", material="aluminium"
):
    return e.experience.note(
        {
            "experiment_id": row["_id"],
            "actor": "agent",
            "operation_id": op,
            "claim": claim,
            "applicability": {
                "domain": "mechanical",
                "phenomena": ["linear_static"],
                "material_models": ["linear_isotropic"],
                "materials": [material],
                "processes": ["machined"],
                "load_regimes": ["static"],
            },
        }
    )


def context(material="aluminium"):
    return {
        "domain": "mechanical",
        "phenomena": ["linear_static"],
        "material_models": ["linear_isotropic"],
        "materials": [material],
        "processes": ["machined"],
        "load_regimes": ["static"],
    }


@pytest.mark.parametrize("driver", ["external", "managed"])
def test_cross_object_transfer_is_a_hypothesis_not_score(tmp_path, driver):
    e = engine(tmp_path)
    a = open_run(e, "mount", driver)
    b = open_run(e, "gripper", driver)
    learned = note(e, a)
    result = e.experience.search(
        {"query": "cantilever deflection", "experiment_id": b["_id"], "applicability": context()}
    )
    assert result["items"][0]["id"] == learned["id"]
    assert result["items"][0]["object_id"] == "mount"
    assert not result["items"][0]["transfers_acceptance"]
    assert result["items"][0]["support"] == "hypothesis"
    assert result["items"][0]["applicability_check"]["requires_new_validation"]
    assert not e.store.list("requests")
    assert e.lifecycle.get(b["_id"])["results"] == []


def test_incompatible_material_load_and_unknown_inputs(tmp_path):
    e = engine(tmp_path)
    row = open_run(e)
    saved = note(e, row)
    query = {"query": "deflection", "applicability": context("PA12")}
    item = e.experience.search(query)["items"][0]
    assert item["applicability_check"]["status"] == "incompatible"
    assert "materials" in item["applicability_check"]["conflicts"]
    assert not e.experience.search({**query, "include_incompatible": False})["items"]
    query["applicability"] = context()
    query["applicability"]["quantities"] = {
        "tip": {"minimum": 1000, "maximum": 1000, "unit": "N", "dimension": "force"}
    }
    saved["applicability"]["quantities"] = {
        "tip": {"minimum": 0, "maximum": 0.1, "unit": "kN", "dimension": "force"}
    }
    from davinci.product.memory_contracts import Applicability

    check = e.experience.applicability(saved, Applicability.model_validate(query["applicability"]))
    assert "tip" in check["conflicts"]
    assert (
        e.experience.search({"query": "deflection"})["items"][0]["applicability_check"]["status"]
        == "needs_review"
    )


def test_notes_cannot_manufacture_support_and_supersession_preserves_bad_claim(tmp_path):
    e = engine(tmp_path)
    row = open_run(e)
    bad = note(e, row, "Use thin cantilever sections for lower deflection.", op="bad")
    good = note(e, row, op="good")
    with pytest.raises(ValueError):
        MemoryNote.model_validate(
            {
                "experiment_id": row["_id"],
                "actor": "agent",
                "operation_id": "forged",
                "claim": "passed",
                "support": "measurement_supported",
            }
        )
    command = {
        "actor": "agent",
        "operation_id": "replace",
        "revision": 0,
        "replacement_id": good["id"],
        "reason": "Incorrect stiffness relationship in prior claim",
    }
    e.experience.supersede(bad["id"], command)
    assert e.experience.supersede(bad["id"], command)["superseded_by"] == good["id"]
    assert {x["id"] for x in e.experience.search({"query": "cantilever"})["items"]} == {good["id"]}
    assert {
        x["id"] for x in e.experience.search({"query": "cantilever", "include_superseded": True})["items"]
    } == {good["id"], bad["id"]}
    with pytest.raises(ValueError, match="cycle"):
        e.experience.supersede(good["id"], {**command, "operation_id": "cycle", "replacement_id": bad["id"]})
    with pytest.raises(Conflict):
        e.experience.supersede(
            good["id"],
            {
                **command,
                "operation_id": "stale",
                "replacement_id": note(e, row, op="next")["id"],
                "revision": 9,
            },
        )


def test_indexed_retrieval_pagination_and_project_isolation(tmp_path, monkeypatch):
    e = engine(tmp_path, "alpha")
    row = open_run(e)
    ids = {note(e, row, op=str(i))["id"] for i in range(12)}
    monkeypatch.setattr(
        e.store, "list", lambda *a, **kw: pytest.fail("Memory retrieval must not list/scan collections")
    )
    query = {"query": "cantilever", "limit": 5}
    seen = []
    while True:
        result = e.experience.search(query)
        seen.extend(x["id"] for x in result["items"])
        if not result["next_cursor"]:
            break
        query["cursor"] = result["next_cursor"]
    assert set(seen) == ids and len(seen) == 12
    sql = []
    e.store.sql.set_trace_callback(sql.append)
    e.experience.search({"query": "cantilever"})
    assert any("experience_text_v1 MATCH" in q and "LIMIT" in q for q in sql)
    other = engine(tmp_path, "beta")
    assert not other.experience.search({"query": "cantilever"})["items"]
    with pytest.raises(KeyError):
        other.experience.get(next(iter(ids)))
    with pytest.raises(KeyError):
        other.experience.export([next(iter(ids))])
    with pytest.raises(KeyError):
        note(other, row)
    # Same actor/opening operation in a different project does not alias a foreign run.
    assert open_run(other)["_id"] != row["_id"]
    # Independent workspace sharing the same document store is still isolated for memory.
    elsewhere = engine(tmp_path / "other", "alpha")
    elsewhere.experience.store = e.store
    assert not elsewhere.experience.search({"query": "cantilever"})["items"]


def test_exact_results_require_all_reproducibility_inputs_and_never_skip_execution(tmp_path):
    e = engine(tmp_path)
    row = evaluated(e, frozen(e))
    result = row["results"][-1]
    observations = e.experience.search({"query": "beam"})["items"]
    observation = next(x for x in observations if x["kind"] == "observation")
    assert observation["support"] == "simulation_supported"
    exact = observation["exact_inputs"]
    assert exact is not None
    found = e.experience.exact(exact)
    assert len(found["items"]) == 1 and not found["cache_enabled"] and not found["reusable_for_acceptance"]
    for key in exact:
        altered = {**exact, key: ("0" * 64 if "sha256" in key else "different")}
        assert not e.experience.exact(altered)["items"], key
    with pytest.raises(ValueError):
        e.experience.exact({"suite_id": row["suite_id"]})
    # Linked reflection is still a hypothesis, even for the managed driver.
    row = e.lifecycle.reflect(
        row["_id"], cmd(row, "reflect"), lesson="Different geometry may also work", result_id=result["id"]
    )
    lesson = next(x for x in e.experience.search({"query": "geometry"})["items"] if x["kind"] == "lesson")
    assert lesson["support"] == "hypothesis"
    # Corrupt source evidence invalidates exact lookup without erasing its historical lesson.
    art = e.store.get("artifacts", result["artifacts"]["model.step"])
    (e.artifacts.root / art["sha256"]).write_bytes(b"corrupted")
    assert not e.experience.exact(exact)["items"]
    assert e.experience.get(observation["id"], verify=True)["evidence_issues"]


def test_export_import_preserves_origin_but_not_local_validation(tmp_path):
    source = engine(tmp_path / "source")
    evaluated(source, frozen(source))
    record = next(
        x for x in source.experience.search({"query": "beam"})["items"] if x["kind"] == "observation"
    )
    bundle = source.experience.export([record["id"]], True)
    dest = engine(tmp_path / "dest")
    command = {"operation_id": "import", "actor": "user", "bundle": bundle}
    imported = dest.experience.import_bundle(command)["items"][0]
    assert imported["origin"] == record["origin"]
    assert imported["support"] == "simulation_supported"  # preserved source claim
    assert imported["local_evidence_status"] == "imported_unverified"
    assert not imported["evidence_issues"]
    assert imported["import_history"][-1]["source_evidence_status"] == "harness_observed"
    assert not dest.experience.exact(record["exact_inputs"])["items"]
    assert dest.experience.import_bundle(command)["items"][0]["id"] == imported["id"]
    with pytest.raises(Conflict):
        dest.experience.import_bundle({**command, "bundle": {**bundle, "records": []}})
    missing = {**bundle, "artifacts": []}
    assert dest.experience.import_bundle({**command, "operation_id": "missing", "bundle": missing})["items"][
        0
    ]["evidence_issues"]
    corrupt = copy.deepcopy(bundle)
    corrupt["artifacts"][0]["data_base64"] = base64.b64encode(b"bad").decode()
    with pytest.raises(ValueError, match="artifact"):
        dest.experience.import_bundle({**command, "operation_id": "bad", "bundle": corrupt})
    forged = copy.deepcopy(bundle)
    forged["records"][0]["support"] = "measurement_supported"
    claimed = dest.experience.import_bundle({**command, "operation_id": "claimed", "bundle": forged})[
        "items"
    ][0]
    assert claimed["local_evidence_status"] == "imported_unverified"
    assert not claimed["transfers_acceptance"]


def test_embedding_adapter_and_missing_vectors_fallback(tmp_path, monkeypatch):
    e = engine(tmp_path, embedding=True)
    monkeypatch.setattr(
        "davinci.product.provider.OpenAI", lambda **kw: pytest.fail("No embedding provider call")
    )
    row = open_run(e)
    record = note(e, row)
    result = e.experience.search({"query": "cantilever deflection"})
    assert result["vector_status"] == "local_hash"
    assert result["items"][0]["ranking"]["semantic_score"] is not None
    e.store.update("experiences_v1", record["id"], {"embedding": None})
    result = e.experience.search({"query": "cantilever deflection"})
    assert result["vector_status"] == "missing_vectors_lexical_fallback"
    assert result["items"][0]["id"] == record["id"]
    assert e.experience.reindex()["processed"] == 1
    assert e.experience.search({"query": "cantilever"})["items"][0]["ranking"]["semantic_score"] is not None


def test_http_public_memory_operations(tmp_path):
    e = engine(tmp_path)
    row = open_run(e)
    with TestClient(create_app(tmp_path, engine=e, run_worker=False)) as client:
        payload = {
            "actor": "agent",
            "operation_id": "note",
            "experiment_id": row["_id"],
            "claim": "Inspect beam stiffness before cutting ribs",
        }
        response = client.post("/api/v2/memory/notes", json=payload)
        assert response.status_code == 201, response.text
        identity = response.json()["id"]
        assert client.post("/api/v2/memory/notes", json=payload).json()["id"] == identity
        assert client.post("/api/v2/memory/notes", json={**payload, "claim": "changed"}).status_code == 409
        assert (
            client.post(
                "/api/v2/memory/notes", json={**payload, "support": "simulation_supported"}
            ).status_code
            == 422
        )
        assert client.get("/api/v2/memory/records/" + identity).status_code == 200
        assert (
            client.post("/api/v2/memory/search", json={"query": "stiffness"}).json()["items"][0]["id"]
            == identity
        )
        assert client.get("/api/v2/memory/records?limit=1").json()["items"][0]["id"] == identity
        exported = client.post("/api/v2/memory/export", json={"ids": [identity]}).json()
        imported = client.post(
            "/api/v2/memory/import", json={"actor": "user", "operation_id": "import", "bundle": exported}
        )
        assert imported.status_code == 200, imported.text
        assert not imported.json()["locally_reproduced"]
        assert client.post("/api/v2/memory/exact", json={"score": 1}).status_code == 422
        assert (
            client.post(
                "/api/v2/memory/capture", json={"experiment_id": row["_id"], "result_id": "forged"}
            ).status_code
            == 404
        )
        assert client.post("/api/v2/memory/reindex", json={}).json()["processed"] == 2
        assert client.get("/api/v2/memory/indexes").json()["automatic_provisioning"] is False


def test_atlas_vector_scores_survive_fusion_and_scope_filter(tmp_path, monkeypatch):
    e = engine(tmp_path, embedding=True)
    row = open_run(e)
    first = note(e, row, op="first")
    second = note(e, row, op="second")
    docs = [e.store.get("experiences_v1", i["id"]) for i in (first, second)]
    foreign = {**docs[0], "_id": "foreign", "id": "foreign", "project_id": "other", "semantic_score": 1.0}
    monkeypatch.setattr(e.store, "experience_page", lambda *a, **kw: docs)
    monkeypatch.setattr(
        e.store,
        "experience_vectors",
        lambda scope, vector, identity: [
            {**docs[0], "semantic_score": 0.1},
            {**docs[1], "semantic_score": 0.95},
            foreign,
        ],
    )
    e.store.db = object()  # deterministic Atlas-vector boundary, no database connection
    result = e.experience.search({"query": "cantilever deflection"})
    assert result["vector_status"] == "atlas_vector"
    assert result["items"][0]["id"] == second["id"]
    assert result["items"][0]["ranking"]["semantic_score"] == 0.95
    assert all(i["id"] != "foreign" for i in result["items"])
    monkeypatch.setattr(
        e.store,
        "experience_vectors",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("unavailable index")),
    )
    assert (
        e.experience.search({"query": "cantilever"})["vector_status"]
        == "vector_index_unavailable_lexical_fallback"
    )


def test_failed_evidence_and_causal_reflections_remain_distinct(tmp_path):
    e = engine(tmp_path)
    evaluated(e, frozen(e), t=2)
    observation = next(
        x for x in e.experience.search({"query": "beam"})["items"] if x["kind"] == "observation"
    )
    assert observation["support"] == "simulation_supported"
    assert observation["failure_modes"] == ["acceptance_limit"]
    assert observation["measured_outcomes"][0]["status"] == "physical_failure"
    assert observation["exact_inputs"]
    assert not observation["transfers_acceptance"]


def test_workspace_move_keeps_durable_memory_namespace(tmp_path):
    import shutil

    original = tmp_path / "original"
    e = engine(original)
    saved = note(e, open_run(e))
    identity = e.experience.scope["workspace_id"]
    e.store.sql.close()
    moved = tmp_path / "moved"
    shutil.move(original, moved)
    restored = engine(moved)
    assert restored.experience.scope["workspace_id"] == identity
    assert restored.experience.search({"query": "cantilever"})["items"][0]["id"] == saved["id"]
