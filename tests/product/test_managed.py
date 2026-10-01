"""Managed stages use deterministic reasoning; only marked integration executes real CAD."""

import copy
import json
import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from test_lifecycle import IMAGE, cmd
from test_simulation import SimulationRunner

from davinci.config import Settings
from davinci.product import recipes
from davinci.product.api import create_app
from davinci.product.contracts import Candidate
from davinci.product.engine import Engine
from davinci.product.lifecycle import Conflict
from davinci.product.managed_contracts import ManagedRequest

DESCRIPTION = (
    "Minimize mass of a rectangular prismatic aluminium cantilever: 40 mm long, 20 mm wide, "
    "thickness 2 to 8 mm, clamped root, transverse tip force 100 N. Nominal E=70000 MPa "
    "and density=0.0027 g/mm3 supplied for an analytic small-deflection screen. "
    "Hard limits: stress <=100 MPa and tip deflection <=0.5 mm. No fatigue, joints or dynamic loads."
)


def requirements():
    inputs = {
        "length_mm": 40,
        "width_mm": 20,
        "thickness_min_mm": 2,
        "thickness_max_mm": 8,
        "force_n": 100,
        "youngs_mpa": 70000,
        "density_g_mm3": 0.0027,
        "stress_limit_mpa": 100,
        "deflection_limit_mm": 0.5,
    }
    return {
        "requirements": [{"id": "strength", "description": DESCRIPTION, "source": "User request"}],
        "assumptions": [
            {
                "description": "Analytic small-deflection screen",
                "source": "User request",
                "applicability": "Rectangular beam, no joints or fatigue; not certification",
            }
        ],
        "recipe": "rectangular-beam-v1",
        "inputs": {
            **inputs,
            "material": "Nominal aluminium",
            "material_provenance": "User-supplied nominal values",
            "input_provenance": {k: "Explicit user request" for k in inputs},
            "phenomena": ["mass", "linear_static", "geometry"],
            "material_model": "linear_isotropic",
            "geometry": "rectangular_prismatic_cantilever",
        },
    }


class DeterministicProvider:
    def __init__(self, engine, row):
        self.engine, self.row = engine, row

    def request(self, key, instruction, context):
        self.engine.model_calls.append(key)
        stage = context["stage"]
        if stage == "requirements":
            return requirements()
        if stage == "test_plan":
            return {
                "plan": context["guidance"]["required_plan"],
                "applicability_explanation": "Matches user beam screen and units",
            }
        if stage == "setup":
            return {
                "evaluator": {
                    "resources": {"evaluate.py": recipes.EVALUATOR},
                    "provenance": "Reused shipped recipe",
                }
            }
        if stage == "propose":
            source = context["guidance"]["builder_example"]
            return Candidate(
                title="Fixture proposal",
                source=source,
                parameters={"thickness": 2 if not context["candidates"] else 4},
            ).model_dump()
        if stage == "diagnose":
            return {
                "lesson": "Thickness changes bending stress; keep fixed loads.",
                "action": "design",
                "explanation": "Use measured stress and deflection margins",
            }
        raise AssertionError(stage)


class ManagedRunner(SimulationRunner):
    def execute(self, entry, files, **kwargs):
        if entry == "/input/_build.py" and "offset=(0, 100, 0)" in files["source.py"]:
            return {"model.step": b"invalid-root"}, "invalid geometry fixture", 0.1
        if entry == "/input/_regions.py" and files["model.step"] == b"invalid-root":
            return (
                {
                    "solver.step": b"invalid-root",
                    "faces.json": b"[]",
                    "geometry.json": json.dumps(
                        {
                            "solids": 1,
                            "planar_faces": 6,
                            "extent": [40, 20, 8],
                            "center": [0, 100, 0],
                            "volume": 6400,
                        }
                    ).encode(),
                },
                "no root match",
                0.1,
            )
        if entry == "/input/_evaluate.py" and "INVALID_EVALUATOR" in files["evaluate.py"]:
            return {"result.json": b'{"passed": true}'}, "invalid authored evaluator", 0.1
        out, log, duration = super().execute(entry, files, **kwargs)
        if entry == "/input/_regions.py":
            t = float(files["model.step"])
            out["geometry.json"] = json.dumps(
                {
                    "solids": 1,
                    "planar_faces": 6,
                    "extent": [40, 20, t],
                    "center": [0, 0, 0],
                    "volume": 800 * t,
                }
            ).encode()
        return out, log, duration


def engine_at(path, provider=DeterministicProvider, runner=None):
    engine = Engine(
        path,
        provider=provider,
        runner=runner or ManagedRunner(),
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
    )
    engine.model_calls = []
    return engine


def request(**kw):
    return ManagedRequest.model_validate(
        {
            "object": {"slug": "beam", "name": "Beam"},
            "description": DESCRIPTION,
            "actor": "user",
            "operation_id": "request-1",
            "mode": "replay",
            "runtime": {
                "image": IMAGE,
                "solver": "numpy beam",
                "provenance": "Deterministic fixture runtime",
            },
            "policy": {"max_candidates": 2, "min_candidates": 2},
            **kw,
        }
    )


def drive(engine, eid, until=None):
    for _ in range(150):
        row = engine.lifecycle.get(eid)
        if until and until(row):
            return row
        if row["managed"]["status"] != "ready" or row["phase"] in (
            "cancelled",
            "interrupted",
            "awaiting_input",
        ):
            return row
        if row["phase"] == "queued":
            engine.lifecycle.execute_scheduled(eid)
        else:
            engine.managed.workflow.tick(eid)
    raise AssertionError(engine.lifecycle.get(eid)["managed"])


def test_request_to_verified_failed_then_improved_without_task_files(tmp_path):
    engine = engine_at(tmp_path)
    row = engine.managed.workflow.start(request())
    assert not (tmp_path / "build.py").exists() and not row["evaluator"] and not row["candidates"]
    row = drive(engine, row["_id"])
    assert row["managed"]["status"] == "completed", row["managed"]
    assert [r["design_accepted"] for r in row["results"]] == [False, True, True]
    assert row["report"]["managed"]["final_evidence_complete"]
    assert len(row["report"]["accepted_candidate_ids"]) == 1
    assert all(v["matched"] for v in row["verifications"]) and len(row["verifications"]) == 3
    actions = [h["action"] for h in row["history"]]
    assert actions.index("verify") < actions.index("freeze") < actions.index("submit_candidate")
    assert row["managed"]["stop_reason"] == "candidate_limit"
    assert len(engine.experience.search({"query": "beam", "experiment_id": row["_id"]})["items"]) > 0


def test_clarifications_persist_and_continue_without_routine_approval(tmp_path):
    class Missing(DeterministicProvider):
        def request(self, key, instruction, context):
            if context["stage"] == "requirements" and not context["answers"]:
                value = requirements()
                value["inputs"] = None
                value["questions"] = {"load": "What transverse tip load in newtons must it carry?"}
                return value
            return super().request(key, instruction, context)

    engine = engine_at(tmp_path, Missing)
    row = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert row["phase"] == "awaiting_input" and not row["candidates"]
    with pytest.raises(ValueError):
        engine.managed.workflow.answer(
            row["_id"], {**cmd(row, "answer").model_dump(), "answers": {"wrong": "100"}}
        )
    row = engine.managed.workflow.answer(
        row["_id"], {**cmd(row, "answer").model_dump(), "answers": {"load": "100 N"}}
    )
    row = drive(engine, row["_id"])
    assert row["managed"]["status"] == "completed"
    assert row["managed"]["answers"][0]["answers"]["load"] == "100 N"


@pytest.mark.parametrize("issue", ["malformed", "relaxed", "physics", "evaluator"])
def test_invalid_authoring_never_freezes_or_models(tmp_path, issue):
    class Invalid(DeterministicProvider):
        def request(self, key, instruction, context):
            data = super().request(key, instruction, context)
            stage = context["stage"]
            if issue == "malformed" and stage == "requirements":
                return {"passed": True}
            if issue == "relaxed" and stage == "test_plan":
                data["plan"]["tests"][0]["criteria"][0]["limit"] = 10000
            if issue == "physics" and stage == "requirements":
                data["inputs"]["phenomena"].append("fatigue")
            if issue == "evaluator" and stage == "setup":
                data["evaluator"]["resources"]["evaluate.py"] = "# INVALID_EVALUATOR"
            return data

    engine = engine_at(tmp_path, Invalid)
    row = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert row["managed"]["status"] == "blocked", row["managed"]
    assert not row["suite_id"] and not row["candidates"]
    if issue == "malformed":
        assert len(engine.model_calls) == 2  # distinct bounded repair requests, never one uncertain retry
    if issue == "evaluator":
        assert row["managed"]["stop_reason"] == "evaluator_verification_failed"
        assert all(not x["matched"] for x in row["verifications"])


def test_restart_checkpoints_cancel_and_external_isolation(tmp_path):
    engine = engine_at(tmp_path)
    row = engine.managed.workflow.start(request())
    # Crash after a paid-stage checkpoint but before its local output is applied.
    engine.managed.workflow.reason(
        row,
        __import__("davinci.product.managed_contracts", fromlist=["RequirementsOutput"]).RequirementsOutput,
        "fixture instruction",
        {"recipes": recipes.catalog()},
    )
    assert len(engine.model_calls) == 1
    replacement = engine_at(tmp_path)
    replacement.recover()
    row = drive(replacement, row["_id"], lambda r: r["managed"]["stage"] == "propose")
    assert not any("-requirements-" in k for k in replacement.model_calls)
    assert row["suite_id"]
    row = replacement.lifecycle.cancel(row["_id"], cmd(row, "cancel"))
    replacement.managed.workflow.tick(row["_id"])
    assert not row["candidates"]
    row = replacement.lifecycle.resume(row["_id"], cmd(row, "resume"))
    assert drive(replacement, row["_id"])["managed"]["status"] == "completed"
    external = replacement.lifecycle.open(
        {
            "object": {"slug": "external", "name": "External"},
            "description": "External request",
            "actor": "coder",
            "operation_id": "external",
            "driver": "external",
        }
    )
    calls = len(replacement.model_calls)
    assert replacement.managed.workflow.tick(external["_id"]) == external
    assert len(replacement.model_calls) == calls


def test_passing_baseline_continues_optimization_and_coordinate_budget(tmp_path):
    class Passing(DeterministicProvider):
        def request(self, key, instruction, context):
            answer = super().request(key, instruction, context)
            if context["stage"] == "propose":
                answer["parameters"]["thickness"] = 8
            return answer

    engine = engine_at(tmp_path, Passing)
    row = drive(
        engine,
        engine.managed.workflow.start(
            request(policy={"max_candidates": 3, "min_candidates": 2, "search": "coordinate"})
        )["_id"],
    )
    assert row["managed"]["status"] == "completed", row["managed"]
    assert len(row["candidates"]) == 4
    assert row["results"][0]["design_accepted"]
    assert row["candidates"][1]["parameters"]["thickness"] < 8
    assert len([k for k in engine.model_calls if "-propose-" in k]) == 1
    assert (
        sum(row["managed"]["solver_reservations"].values())
        <= row["managed"]["policy"]["solver_compute_seconds"]
    )


def test_capability_and_compute_budget_before_candidates(tmp_path):
    runner = ManagedRunner()
    runner.capacity = {**runner.capacity, "available": False, "reason": "Solver unavailable"}
    engine = engine_at(tmp_path / "missing", runner=runner)
    row = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert row["managed"]["stop_reason"] == "unavailable_capability"
    assert not row["fixtures"] and not row["candidates"]
    engine = engine_at(tmp_path / "budget")
    row = drive(engine, engine.managed.workflow.start(request(policy={"solver_compute_seconds": 1}))["_id"])
    assert row["managed"]["stop_reason"] == "solver_budget_exhausted"
    assert not row["candidates"]


def test_public_http_worker_and_idempotency(tmp_path):
    engine = engine_at(tmp_path)
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        body = request().model_dump()
        response = client.post("/api/v2/managed-experiments", json=body)
        assert response.status_code == 202, response.text
        row = response.json()
        assert client.post("/api/v2/managed-experiments", json=body).json()["_id"] == row["_id"]
        other = copy.deepcopy(body)
        other["description"] = "Changed request"
        assert client.post("/api/v2/managed-experiments", json=other).status_code == 409
        import time

        for _ in range(300):
            status = client.get("/api/v2/experiments/" + row["_id"]).json()
            if status["managed"]["status"] == "completed":
                break
            time.sleep(0.1)
        assert status["managed"]["status"] == "completed", status
        assert client.get("/api/v2/test-recipes").json()[0]["id"] == "rectangular-beam-v1"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Explicit local Docker CAD opt-in")
def test_native_request_without_pre_authored_directory(tmp_path):
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    from davinci.runner import Runner

    engine = engine_at(
        tmp_path,
        runner=Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key="")),
    )
    req = request(
        runtime={
            "image": image,
            "solver": "CadQuery + NumPy linear beam",
            "provenance": "Local pinned CAD runtime",
        }
    )
    row = drive(engine, engine.managed.workflow.start(req)["_id"])
    assert row["managed"]["status"] == "completed", row["managed"]
    assert [r["design_accepted"] for r in row["results"]] == [False, True, True]
    assert all(v["matched"] for v in row["verifications"])
    assert row["report"]["managed"]["final_evidence_complete"]
    assert all(r["manifest"]["complete"] for r in row["results"])


def test_evaluator_repair_uses_new_version_and_never_self_certifies(tmp_path):
    class Repair(DeterministicProvider):
        def request(self, key, instruction, context):
            answer = super().request(key, instruction, context)
            if context["stage"] == "setup" and self.row["managed"]["setup_repairs"] == 0:
                answer["evaluator"]["resources"]["evaluate.py"] = "# INVALID_EVALUATOR"
            return answer

    engine = engine_at(tmp_path, Repair)
    row = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert row["managed"]["status"] == "completed", row["managed"]
    failed = [v for v in row["verifications"] if not v["matched"]]
    assert failed and failed[0]["evaluator_id"] != row["evaluator_id"]
    assert all(v["matched"] for v in row["verifications"] if v["evaluator_id"] == row["evaluator_id"])


def test_post_freeze_defect_opens_linked_revision_and_reruns(tmp_path):
    class Correct(DeterministicProvider):
        def request(self, key, instruction, context):
            answer = super().request(key, instruction, context)
            if context["stage"] == "diagnose" and not self.row.get("parent_experiment_id"):
                answer.update(
                    action="evaluator_defect",
                    explanation="Suspected evaluator implementation issue; rerun evidence",
                )
            if context["stage"] == "setup" and self.row.get("parent_experiment_id"):
                answer["evaluator"]["resources"]["evaluate.py"] += (
                    "\n# documented implementation correction\n"
                )
            return answer

    engine = engine_at(tmp_path, Correct)
    parent = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert parent["managed"]["stop_reason"] == "superseded_by_evaluator_revision"
    suite = parent["suite_id"]
    child = drive(engine, parent["managed"]["correction_id"])
    assert child["managed"]["status"] == "completed", child["managed"]
    assert child["parent_experiment_id"] == parent["_id"]
    assert child["suite_id"] != suite
    assert engine.lifecycle.get(parent["_id"])["suite_id"] == suite
    assert child["candidates"][0]["source_artifact"] == parent["candidates"][0]["source_artifact"]
    assert child["candidates"][0]["parameters"] == parent["candidates"][0]["parameters"]
    assert child["results"][0]["suite_id"] != parent["results"][0]["suite_id"]
    assert child["managed"]["correction"]["affected_candidate_ids"] == [parent["candidates"][0]["id"]]


def test_missing_final_evidence_cannot_report_search_pass_as_final_acceptance(tmp_path):
    engine = engine_at(tmp_path)
    row = drive(
        engine,
        engine.managed.workflow.start(request())["_id"],
        lambda r: r["managed"]["stage"] == "final_evaluate",
    )
    assert any(r["design_accepted"] for r in row["results"])
    engine.runner.fail = "resource_exhaustion"
    row = drive(engine, row["_id"])
    assert row["managed"]["status"] == "completed"
    assert not row["report"]["managed"]["final_evidence_complete"]
    assert not row["report"]["accepted_candidate_ids"]


def test_request_checkpoints_avoid_duplicate_paid_calls_and_uncertain_retry(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from davinci.product.managed_contracts import RequirementsOutput
    from davinci.product.provider import Provider, UncertainRequest

    engine = engine_at(tmp_path, Provider)
    engine.credentials.openai_api_key = "fixture-key-not-a-credential"
    row = engine.managed.workflow.start(request(mode="live"))
    calls = []

    def create(**kw):
        calls.append(kw)
        return SimpleNamespace(id="fixture-response", usage=None, output_text=json.dumps(requirements()))

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    original_finish = engine.lifecycle._finish

    def crash(*a, **kw):
        raise RuntimeError("process lost after provider checkpoint")

    monkeypatch.setattr(engine.lifecycle, "_finish", crash)
    with pytest.raises(RuntimeError):
        engine.managed.workflow.reason(row, RequirementsOutput, "requirements")
    monkeypatch.setattr(engine.lifecycle, "_finish", original_finish)
    engine.recover()
    row = engine.lifecycle.get(row["_id"])
    row = engine.lifecycle.resume(row["_id"], cmd(row, "resume"))
    engine.managed.workflow.tick(row["_id"])
    assert len(calls) == 1
    assert engine.lifecycle.get(row["_id"])["managed"]["stage"] == "retrieve"
    assert engine.store.get("runs", row["_id"])["spent_usd"] > 0

    other = engine.managed.workflow.start(request(mode="live", operation_id="timeout"))

    def timeout(**kw):
        calls.append(kw)
        raise TimeoutError("fixture timeout")

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=timeout)),
    )
    with pytest.raises(UncertainRequest):
        engine.managed.workflow.tick(other["_id"])
    other = engine.lifecycle.get(other["_id"])
    assert other["phase"] == "interrupted"
    with pytest.raises(Conflict, match="uncertain"):
        engine.lifecycle.resume(other["_id"], cmd(other, "resume"))
    assert len(calls) == 2


def test_cancel_during_simulation_resumes_safely(tmp_path):
    engine = engine_at(tmp_path)
    row = drive(
        engine,
        engine.managed.workflow.start(request())["_id"],
        lambda r: r["managed"]["stage"] == "simulate" and r["phase"] == "queued",
    )
    original = engine.runner.execute

    def execute(*a, **kw):
        current = engine.lifecycle.get(row["_id"])
        if current["phase"] != "cancelled":
            engine.lifecycle.cancel(row["_id"], cmd(current, "cancel-during-job"))
        return original(*a, **kw)

    engine.runner.execute = execute
    engine.lifecycle.execute_scheduled(row["_id"])
    row = engine.lifecycle.get(row["_id"])
    assert row["phase"] == "cancelled" and not row["results"][-1]["design_accepted"]
    engine.runner.execute = original
    row = engine.lifecycle.resume(row["_id"], cmd(row, "resume"))
    row = drive(engine, row["_id"])
    assert row["managed"]["status"] == "completed", row["managed"]


def test_independent_geometry_and_oracle_reject_evaluator_claims(tmp_path):
    class Spoof(ManagedRunner):
        def execute(self, entry, files, **kwargs):
            out, log, duration = super().execute(entry, files, **kwargs)
            if entry == "/input/_evaluate.py":
                data = json.loads(out["result.json"])
                data["metrics"]["stress_mpa"]["value"] = 0
                out["result.json"] = json.dumps(data).encode()
            return out, log, duration

    engine = engine_at(tmp_path, runner=Spoof())
    row = drive(engine, engine.managed.workflow.start(request())["_id"])
    assert not row["suite_id"] and not row["candidates"]
    assert row["verifications"][0]["result"]["reason"] == "verification_failed"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_LIVE_SMOKE") != "1", reason="Separately opt-in paid model smoke")
def test_live_managed_request_opt_in(tmp_path):
    """Never enabled merely by a credential existing. Budget is explicitly required."""
    from davinci.product.provider import Provider

    key = os.environ.get("OPENAI_API_KEY")
    budget = float(os.environ["DAVINCI_LIVE_BUDGET_USD"])
    assert key and 0 < budget <= 10
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    engine = Engine(
        tmp_path, provider=Provider, credentials=Settings(_env_file=None, openai_api_key=key, mongodb_uri="")
    )
    row = engine.managed.workflow.start(
        request(
            mode="live",
            budget_usd=budget,
            runtime={
                "image": image,
                "solver": "CadQuery + NumPy beam screen",
                "provenance": "Explicit paid smoke",
            },
        )
    )
    row = drive(engine, row["_id"])
    assert row["managed"]["status"] in ("completed", "awaiting_input", "blocked")
    assert row["spent_usd"] <= budget
    # A blocked/clarifying smoke is operational evidence, never a physical success claim.
    print(
        json.dumps(
            {
                "phase": row["phase"],
                "stage": row["managed"]["stage"],
                "spent_usd": row["spent_usd"],
                "status": row["managed"]["status"],
                "accepted": (row.get("report") or {}).get("accepted_candidate_ids", []),
            }
        )
    )


def test_managed_cli_uses_localhost_execution_owner(tmp_path, monkeypatch):
    import socket
    import sys
    import threading
    import time

    import uvicorn

    engine = engine_at(tmp_path)
    engine.credentials.openai_api_key = "deterministic-provider-fixture"
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    (tmp_path / "workspace.yaml").write_text(f"storage: local\nport: {port}\n")
    engine.options.port = port
    original = subprocess.check_output

    def resolve(args, **kw):
        if args[:3] == ["docker", "image", "inspect"]:
            return IMAGE + "\n"
        return original(args, **kw)

    monkeypatch.setattr(subprocess, "check_output", resolve)
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path, engine=engine), log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.01)
        assert server.started

        def cli(*args):
            result = subprocess.run(
                [sys.executable, "-m", "davinci.product.cli", "--workspace", str(tmp_path), "managed", *args],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return json.loads(result.stdout)["data"]

        assert cli("recipes")[0]["id"] == "rectangular-beam-v1"
        row = cli(
            "request",
            "--description",
            DESCRIPTION,
            "--object",
            "beam",
            "--operation-id",
            "cli-1",
            "--max-candidates",
            "2",
        )
        assert row["driver"] == "managed" and row["mode"] == "live"
        for _ in range(200):
            current = engine.lifecycle.get(row["_id"])
            if current["managed"]["status"] == "completed":
                break
            time.sleep(0.1)
        assert cli("status", row["_id"])["managed"]["status"] == "completed"
        assert len(cli("results", row["_id"])["results"]) == 3
        assert cli("report", row["_id"])["report"]["accepted_candidate_ids"]
    finally:
        server.should_exit = True
        thread.join(20)
        sock.close()
        assert not thread.is_alive()
