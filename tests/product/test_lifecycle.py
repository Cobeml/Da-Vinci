"""Provider-independent lifecycle tests: deterministic proposals, no keys or network."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.contracts import Candidate, Command, Evaluator, OpenExperiment, Plan, Runtime
from davinci.product.engine import Engine
from davinci.product.lifecycle import Conflict
from davinci.runner import SandboxError

IMAGE = "sha256:" + "a" * 64
SOURCE = """import cadquery as cq

def build(parameters, interfaces):
    model = cq.Workplane('XY').box(40, 20, parameters['thickness'])
    return cq.Assembly(model)
"""
EVALUATOR = """import cadquery as cq
import numpy as np

def evaluate(step, request):
    shape = cq.importers.importStep(step)
    solid = shape.val()
    bb = solid.BoundingBox()
    t = bb.zlen
    valid = (len(shape.solids().vals()) == 1 and solid.isValid() and
             abs(bb.xlen - 40) < 1e-5 and abs(bb.ylen - 20) < 1e-5 and
             abs(solid.Volume() - 40*20*t) < 1e-4)
    load = request['test']['fixed_inputs']['force_n']
    youngs = request['materials'][0]['properties']['youngs']['value']
    density = request['materials'][0]['properties']['density']['value']
    inertia = 20*t**3/12
    # Euler-Bernoulli cantilever: free-end translation and rotation stiffness.
    stiffness = youngs*inertia / 40**3 * np.array([[12., -6*40], [-6*40, 4*40**2]])
    displacement = np.linalg.solve(stiffness, np.array([load, 0.]))[0]
    values = {'mass_g': (solid.Volume()*density, 'g'),
              'stress_mpa': (6*load*40/(20*t*t), 'MPa'),
              'deflection_mm': (float(displacement), 'mm')}
    return {'test_id': request['test']['id'], 'status': 'pass', 'reason': 'ok',
            'applicable': valid, 'mesh_valid': True, 'bindings': {'root': valid},
            'metrics': {k: {'value': v, 'unit': u, 'numerical_error': .00001, 'uncertainty': 0.}
                        for k, (v, u) in values.items()}}
"""


def plan():
    return Plan.model_validate(
        {
            "requirements": [
                {
                    "id": "strength",
                    "description": "Cantilever supports 100 N",
                    "source": "fixture specification",
                }
            ],
            "assumptions": [
                {
                    "description": "Linear elastic rectangular beam",
                    "source": "Euler-Bernoulli theory",
                    "applicability": "small deflections; no fatigue or local fixture stress",
                }
            ],
            "materials": [
                {
                    "name": "reference aluminium",
                    "provenance": "nominal fixture values, not batch certification",
                    "properties": {
                        "youngs": {"value": 70000, "unit": "MPa", "dimension": "pressure"},
                        "density": {"value": 0.0027, "unit": "g/mm3", "dimension": "density"},
                    },
                }
            ],
            "interfaces": [
                {
                    "id": "root",
                    "description": "40 by 20 mm beam envelope",
                    "binding_rule": "check STEP bounding box and rectangular volume",
                    "unit": "mm",
                    "tolerance": 1e-5,
                }
            ],
            "design_schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["thickness"],
                "properties": {"thickness": {"type": "number", "minimum": 1, "maximum": 10}},
            },
            "design_units": {"thickness": "mm"},
            "objective": {"metric": "mass_g", "direction": "minimize", "target": 1},
            "tests": [
                {
                    "id": "beam",
                    "requirements": ["strength"],
                    "capability": "linear_beam_screen",
                    "applicability": "Rectangular prismatic cantilever only",
                    "fixed_inputs": {"force_n": 100},
                    "load_cases": [
                        {
                            "id": "tip",
                            "description": "vertical tip force",
                            "quantities": {"force": {"value": 100, "unit": "N", "dimension": "force"}},
                            "boundary_conditions": "clamped root; free tip",
                        }
                    ],
                    "metrics": {"mass_g": "g", "stress_mpa": "MPa", "deflection_mm": "mm"},
                    "accuracy": {
                        m: {
                            "method": "analytic beam reference comparison",
                            "max_numerical_error": 0.01,
                            "max_uncertainty": 1,
                        }
                        for m in ("mass_g", "stress_mpa", "deflection_mm")
                    },
                    "mesh_rule": "one exact prismatic beam element; independently verify STEP dimensions and volume",
                    "criteria": [
                        {"metric": "stress_mpa", "operator": "<=", "limit": 100, "unit": "MPa"},
                        {"metric": "deflection_mm", "operator": "<=", "limit": 0.5, "unit": "mm"},
                    ],
                }
            ],
        }
    )


def values(thickness):
    return {
        "mass_g": 40 * 20 * thickness * 0.0027,
        "stress_mpa": 6 * 100 * 40 / (20 * thickness**2),
        "deflection_mm": 100 * 40**3 / (3 * 70000 * (20 * thickness**3 / 12)),
    }


class FixtureRunner:
    cancelled = staticmethod(lambda: False)

    def execute(self, entry, files, **kwargs):
        if self.cancelled():
            raise SandboxError("cancelled", reason="cancelled")
        if entry == "/input/_preview.py":
            return {}, "Preview intentionally absent in orchestration fixture", 0
        if entry == "/input/_build.py":
            params = json.loads(files["request.json"])["parameters"]
            return (
                {"model.step": str(params["thickness"]).encode(), "result.json": b'{"forged":true}'},
                "fixture build",
                0.1,
            )
        request = json.loads(files["request.json"])
        t = float(files["model.step"])
        result = {
            "test_id": request["test"]["id"],
            "status": "pass",
            "reason": "ok",
            "applicable": True,
            "mesh_valid": True,
            "bindings": {"root": True},
            "metrics": {
                k: {
                    "value": v,
                    "unit": request["test"]["metrics"][k],
                    "numerical_error": 0.00001,
                    "uncertainty": 0,
                }
                for k, v in values(t).items()
            },
        }
        assert "source.py" not in files
        assert "forged" not in files.get("result.json", "")
        return {"result.json": json.dumps(result).encode()}, "fixture solver", 0.1


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr("davinci.product.provider.OpenAI", lambda **kw: pytest.fail("No model calls allowed"))
    return Engine(
        tmp_path,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        runner=FixtureRunner(),
    )


def cmd(row, operation):
    return Command(actor=row["actor"], revision=row["revision"], operation_id=operation)


def opened(engine, driver="external"):
    return engine.lifecycle.open(
        OpenExperiment(
            object={"slug": "beam", "name": "Beam"},
            description="Reduce beam mass under fixed tip loading",
            actor="test-author",
            operation_id="open",
            driver=driver,
        )
    )


def configured(engine, driver="external"):
    row = opened(engine, driver)
    return engine.lifecycle.update_plan(
        row["_id"],
        cmd(row, "plan"),
        plan(),
        Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="test fixture"),
        Runtime(image=IMAGE, solver="CadQuery + numpy linear beam", provenance="deterministic test runtime"),
    )


def verification(row, t):
    return {
        "test_id": "beam",
        "fixture_artifact": row["fixtures"][-1]["artifact"],
        "expected_status": "pass" if t == 4 else "physical_failure",
        "reference_metrics": {
            k: {"value": v, "unit": row["plan"]["tests"][0]["metrics"][k], "dimension": "reference"}
            for k, v in values(t).items()
        },
        "tolerances": {k: 0.0001 for k in values(t)},
        "provenance": "independent closed-form cantilever references",
    }


def frozen(engine, driver="external"):
    row = configured(engine, driver)
    for t in (4, 2):
        row = engine.lifecycle.fixture(
            row["_id"], cmd(row, f"fixture-{t}"), step=str(t).encode(), provenance="reference fixture"
        )
        row = engine.lifecycle.verify(row["_id"], cmd(row, f"verify-{t}"), verification(row, t))
    return engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"))


def candidate(t=4, source=SOURCE):
    return Candidate(title="Beam", parameters={"thickness": t}, source=source)


def evaluated(engine, row, t=4):
    row = engine.lifecycle.submit_candidate(
        row["_id"], cmd(row, f"candidate-{len(row['candidates'])}"), candidate(t)
    )
    return engine.lifecycle.request_evaluation(row["_id"], cmd(row, f"evaluate-{len(row['candidates'])}"))


def test_draft_needs_no_builder_and_state_order(engine):
    row = opened(engine)
    assert row["plan"]["design_schema"] and not row["candidates"]
    with pytest.raises(Conflict):
        engine.lifecycle.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())
    with pytest.raises(ValueError):
        engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"))
    p = plan().model_dump()
    p["requirements"][0]["resolved"] = False
    row = engine.lifecycle.update_plan(row["_id"], cmd(row, "incomplete"), p)
    assert row["phase"] == "awaiting_input" and row["pending_input"]
    with pytest.raises(Conflict):
        engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"))


def test_verified_workflow_targets_and_hypotheses(engine):
    row = frozen(engine)
    row = evaluated(engine, row)
    result = row["results"][-1]
    assert result["execution_completed"] and result["evidence_complete"] and result["design_accepted"]
    assert result["objective_target_attained"] is False  # target is not a hard constraint
    row = engine.lifecycle.reflect(row["_id"], cmd(row, "reflect"), lesson="Thinner beam might work")
    assert row["experiences"][0]["support"] == "hypothesis"
    row = engine.lifecycle.finalize(row["_id"], cmd(row, "finalize"))
    assert row["report"]["accepted_candidate_ids"]
    assert engine.lifecycle.retrieve("beam")[0]["transfers_acceptance"] is False


def test_suite_identity_immutable_builder_independent_and_revision(engine):
    row = frozen(engine)
    suite = row["suite_id"]
    with pytest.raises(Conflict):
        engine.lifecycle.update_plan(row["_id"], cmd(row, "edit"), plan())
    row = evaluated(engine, row)
    row = engine.lifecycle.reflect(
        row["_id"], cmd(row, "reflect"), lesson="Try another source", result_id=row["results"][-1]["id"]
    )
    row = engine.lifecycle.submit_candidate(
        row["_id"], cmd(row, "new-source"), candidate(4, SOURCE + "\n# different builder\n")
    )
    assert row["suite_id"] == suite
    assert row["candidates"][0]["candidate_version"] != row["candidates"][1]["candidate_version"]
    new = engine.lifecycle.revise(
        row["_id"],
        OpenExperiment(
            object={"slug": "beam", "name": "Beam"},
            description="Correct evaluator",
            actor=row["actor"],
            operation_id="revision",
            parent_experiment_id=row["_id"],
        ),
    )
    assert new["phase"] == "draft" and not new["results"] and not new["verifications"]
    assert engine.lifecycle.get(row["_id"])["suite_id"] == suite


def test_revision_ownership_and_idempotence(engine):
    row = opened(engine)
    command = cmd(row, "plan")
    updated = engine.lifecycle.update_plan(row["_id"], command, plan())
    assert engine.lifecycle.update_plan(row["_id"], command, plan()) == updated
    p = plan().model_dump()
    p["objective"]["target"] = 2
    with pytest.raises(Conflict, match="identifier"):
        engine.lifecycle.update_plan(row["_id"], command, p)
    with pytest.raises(Conflict, match="Revision"):
        engine.lifecycle.update_plan(row["_id"], cmd(row, "stale"), p)
    with pytest.raises(Conflict, match="owner"):
        engine.lifecycle.update_plan(
            row["_id"], Command(actor="other", revision=updated["revision"], operation_id="bad"), p
        )


def test_concurrent_submission_two_store_connections(engine):
    row = frozen(engine)
    other = Engine(
        engine.workspace,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        runner=FixtureRunner(),
    )

    def submit(pair):
        index, life = pair
        try:
            return life.submit_candidate(row["_id"], cmd(row, str(index)), candidate())
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, enumerate([engine.lifecycle, other.lifecycle])))
    assert sum(r is not None for r in results) == 1
    assert len(engine.lifecycle.get(row["_id"])["candidates"]) == 1


def test_missing_verification_and_coverage(engine):
    row = configured(engine)
    with pytest.raises(ValueError, match="verification incomplete"):
        engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"))
    p = plan().model_dump()
    p["requirements"].append({"id": "fatigue", "description": "Fatigue life", "source": "user"})
    row = engine.lifecycle.update_plan(
        row["_id"], cmd(row, "missing-coverage"), p, row["evaluator"], row["runtime"]
    )
    with pytest.raises(ValueError, match="coverage"):
        engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"), draft_only=True)


@pytest.mark.parametrize(
    "problem,expected",
    [
        ("missing", "not_run"),
        ("units", "invalid_setup"),
        ("binding", "invalid_setup"),
        ("accuracy", "numerical_failure"),
        ("physics", "unsupported_capability"),
    ],
)
def test_incomplete_evidence_never_accepts(engine, monkeypatch, problem, expected):
    row = frozen(engine)
    original = engine.runner.execute

    def execute(entry, files, **kw):
        out, log, duration = original(entry, files, **kw)
        if entry == "/input/_evaluate.py":
            raw = json.loads(out["result.json"])
            if problem == "missing":
                raw["metrics"].pop("mass_g")
            elif problem == "units":
                raw["metrics"]["mass_g"]["unit"] = "kg"
            elif problem == "binding":
                raw["bindings"] = {}
            elif problem == "accuracy":
                raw["metrics"]["mass_g"]["numerical_error"] = 100
            else:
                raw["applicable"] = False
            out["result.json"] = json.dumps(raw).encode()
        return out, log, duration

    monkeypatch.setattr(engine.runner, "execute", execute)
    row = evaluated(engine, row)
    result = row["results"][-1]
    assert result["tests"][0]["status"] == expected
    assert not result["design_accepted"] and not result["evidence_complete"]


@pytest.mark.parametrize(
    "reason,status",
    [
        ("timeout", "not_run"),
        ("resource_exhaustion", "not_run"),
        ("cancelled", "not_run"),
        ("unavailable_runtime", "unsupported_capability"),
        ("solver_error", "invalid_setup"),
    ],
)
def test_build_failures_distinguished(engine, monkeypatch, reason, status):
    row = frozen(engine)

    def fail(*a, **kw):
        raise SandboxError("fixture failure", reason=reason)

    monkeypatch.setattr(engine.runner, "execute", fail)
    row = evaluated(engine, row)
    result = row["results"][-1]
    assert result["tests"][0]["status"] == status
    assert not result["design_accepted"]


def test_physical_failure_is_complete_evidence(engine):
    row = evaluated(engine, frozen(engine), 2)
    assert row["results"][-1]["evidence_complete"]
    assert not row["results"][-1]["design_accepted"]
    assert row["results"][-1]["tests"][0]["status"] == "physical_failure"


def test_restart_is_fenced_no_automatic_execution(engine, monkeypatch):
    row = frozen(engine)
    row = engine.lifecycle.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())

    def crash(*a, **kw):
        raise RuntimeError("simulated process loss")

    original = engine.runner.execute
    monkeypatch.setattr(engine.runner, "execute", crash)
    with pytest.raises(RuntimeError):
        engine.lifecycle.request_evaluation(row["_id"], cmd(row, "evaluation"))
    engine.recover()
    row = engine.lifecycle.get(row["_id"])
    assert row["phase"] == "interrupted" and row["job"]["status"] == "interrupted"
    assert not row["results"]
    row = engine.lifecycle.resume(row["_id"], cmd(row, "resume"))
    assert row["phase"] == "candidate_submitted"
    monkeypatch.setattr(engine.runner, "execute", original)
    row = engine.lifecycle.request_evaluation(row["_id"], cmd(row, "retry"))
    assert len(row["results"]) == 1 and row["results"][0]["design_accepted"]


def test_cancel_during_execution_cannot_accept(engine, monkeypatch):
    row = frozen(engine)
    original = engine.runner.execute

    def execute(entry, files, **kw):
        out = original(entry, files, **kw)
        if entry == "/input/_evaluate.py":
            current = engine.lifecycle.get(row["_id"])
            engine.lifecycle.cancel(row["_id"], cmd(current, "cancel"))
        return out

    monkeypatch.setattr(engine.runner, "execute", execute)
    row = evaluated(engine, row)
    assert row["phase"] == "cancelled" and not row["results"][-1]["design_accepted"]


def test_draft_only_never_accepted(engine, monkeypatch):
    row = configured(engine)
    row = engine.lifecycle.fixture(row["_id"], cmd(row, "ref"), step=b"4", provenance="fixture")
    original = engine.runner.execute

    def unavailable(*a, **kw):
        raise SandboxError("missing runtime", reason="unavailable_runtime")

    monkeypatch.setattr(engine.runner, "execute", unavailable)
    row = engine.lifecycle.verify(row["_id"], cmd(row, "verify-unavailable"), verification(row, 4))
    monkeypatch.setattr(engine.runner, "execute", original)
    row = engine.lifecycle.freeze(row["_id"], cmd(row, "draft-freeze"), draft_only=True)
    row = evaluated(engine, row)
    assert row["results"][-1]["evidence_complete"] and not row["results"][-1]["design_accepted"]


def test_api_and_legacy_adapter(engine):
    engine.store.insert("runs", {"_id": "old", "status": "completed", "config": {"run": {"mode": "replay"}}})
    old = engine.lifecycle.get("old")
    assert old["guarantees"] == "legacy-unverified-coverage" and not old["test_first_verified"]
    assert "lifecycle_version" not in engine.store.get("runs", "old")
    client = TestClient(create_app(engine.workspace, engine=engine, run_worker=False))
    body = {
        "object": {"slug": "api", "name": "API"},
        "description": "draft",
        "actor": "agent",
        "operation_id": "api",
    }
    result = client.post("/api/v2/experiments", json=body)
    assert result.status_code == 201
    row = result.json()
    assert (
        client.post(
            f"/api/v2/experiments/{row['_id']}/freeze", json=cmd(row, "freeze").model_dump()
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v2/experiments/{row['_id']}/candidates",
            json={**cmd(row, "candidate").model_dump(), "candidate": candidate().model_dump()},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v2/experiments", json=body, headers={"origin": "https://untrusted.test"}
        ).status_code
        == 403
    )


def test_managed_uses_same_lifecycle_without_paid_calls(engine):
    class ProviderFixture:
        def __init__(self, *args):
            pass

        def request(self, stage, instruction, context):
            if "propose" in stage:
                return candidate().model_dump()
            if "reflect" in stage:
                return {"lesson": "Measured fixture passed; thinner remains a hypothesis"}
            return {"plan": plan().model_dump(), "evaluator": None, "runtime": None}

    engine.provider_type = ProviderFixture
    # Live flag is independent of driver; only the injected fixture supplies reasoning.
    engine.credentials.openai_api_key = "fixture-placeholder"
    row = frozen(engine, "managed")
    row = engine.managed.advance(row["_id"], cmd(row, "proposal"), "propose")
    assert row["phase"] == "candidate_submitted"
    row = engine.lifecycle.request_evaluation(row["_id"], cmd(row, "evaluate"))
    row = engine.managed.advance(row["_id"], cmd(row, "reflection"), "reflect")
    assert row["phase"] == "reflected"
    row = engine.lifecycle.finalize(row["_id"], cmd(row, "report"))
    assert row["report"]["accepted_candidate_ids"]
    assert not engine.store.list("requests")


def test_optional_embeddings_do_not_require_keys(engine):
    from davinci.product.provider import Provider

    row = opened(engine)
    assert Provider(engine, row).embed("test", "beam") is None


def test_verification_invalidated_by_plan_edit(engine):
    row = frozen(engine)
    parent = row["_id"]
    child = engine.lifecycle.revise(
        parent,
        OpenExperiment(
            object={"slug": "beam", "name": "Beam"},
            description="New limits",
            actor=row["actor"],
            operation_id="new-plan",
            parent_experiment_id=parent,
        ),
    )
    changed = plan().model_dump()
    changed["tests"][0]["criteria"][0]["limit"] = 200
    child = engine.lifecycle.update_plan(
        child["_id"], cmd(child, "change-limit"), changed, child["evaluator"], child["runtime"]
    )
    assert child["plan_id"] != row["plan_id"]
    assert child["evaluator_id"] == row["evaluator_id"]
    assert not child["verifications"] and not child["results"]
    with pytest.raises(ValueError, match="verification incomplete"):
        engine.lifecycle.freeze(child["_id"], cmd(child, "freeze"))


def test_changed_harness_requires_linked_suite(engine, monkeypatch):
    row = frozen(engine)
    monkeypatch.setattr("davinci.product.lifecycle.execution_identity", lambda: ("changed", {}))
    row = engine.lifecycle.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())
    with pytest.raises(Conflict, match="implementation changed"):
        engine.lifecycle.request_evaluation(row["_id"], cmd(row, "evaluate"))


def test_managed_author_records_missing_information(engine):
    class AuthorFixture:
        def __init__(self, *args):
            pass

        def request(self, stage, instruction, context):
            assert "schemas" in context
            missing = plan().model_dump()
            missing["requirements"][0]["resolved"] = False
            missing["requirements"][0]["description"] = "What is the maximum tip load?"
            return {"plan": missing, "evaluator": None, "runtime": None}

    engine.provider_type = AuthorFixture
    engine.credentials.openai_api_key = "fixture-placeholder"
    row = opened(engine, "managed")
    row = engine.managed.advance(row["_id"], cmd(row, "author"), "author")
    assert row["phase"] == "awaiting_input" and "tip load" in row["pending_input"][0]
    assert not row["candidates"] and not row["suite_id"]


def test_managed_budget_and_uncertain_requests_are_not_repeated(engine, monkeypatch):
    from types import SimpleNamespace

    from davinci.product.provider import UncertainRequest

    row = frozen(engine, "managed")
    engine.credentials.openai_api_key = "fixture-placeholder"
    calls = []

    def timeout(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("fixture timeout")

    monkeypatch.setattr(
        "davinci.product.provider.OpenAI",
        lambda **kw: SimpleNamespace(responses=SimpleNamespace(create=timeout)),
    )
    command = cmd(row, "generate")
    with pytest.raises(UncertainRequest):
        engine.managed.advance(row["_id"], command, "propose")
    row = engine.lifecycle.get(row["_id"])
    assert row["phase"] == "interrupted" and row["spent_usd"] > 0
    engine.managed.advance(row["_id"], command, "propose")
    assert len(calls) == 1
    with pytest.raises(Conflict, match="uncertain"):
        engine.lifecycle.resume(row["_id"], cmd(row, "resume"))


def test_pending_evaluation_blocks_other_driver(engine, monkeypatch):
    row = frozen(engine)
    second = engine.lifecycle.open(
        OpenExperiment(
            object={"slug": "other", "name": "Other"},
            description="Independent task",
            driver="managed",
            actor="second",
            operation_id="open-second",
        )
    )
    original = engine.runner.execute

    def execute(entry, files, **kwargs):
        if entry == "/input/_preview.py":
            return {}, "Preview intentionally absent in orchestration fixture", 0
        if entry == "/input/_build.py":
            engine.credentials.openai_api_key = "fixture-placeholder"
            with pytest.raises(Conflict, match="Another execution"):
                engine.managed.advance(second["_id"], cmd(second, "author"), "author")
        return original(entry, files, **kwargs)

    monkeypatch.setattr(engine.runner, "execute", execute)
    row = evaluated(engine, row)
    assert row["results"][-1]["design_accepted"]
    assert not engine.store.list("requests")


def test_no_client_supplied_results_and_reference_tampering(engine):
    row = configured(engine)
    client = TestClient(create_app(engine.workspace, engine=engine, run_worker=False))
    assert (
        client.post(f"/api/v2/experiments/{row['_id']}/results", json={"status": "pass"}).status_code == 405
    )
    body = {**cmd(row, "submit").model_dump(), "candidate": candidate().model_dump(), "evaluator": {}}
    assert client.post(f"/api/v2/experiments/{row['_id']}/candidates", json=body).status_code == 422
    with pytest.raises(ValueError, match="unavailable"):
        engine.lifecycle.freeze(row["_id"], cmd(row, "unverified"), draft_only=True)


def test_legacy_suite_identity_excludes_builder(engine):
    import yaml

    from davinci.product.compatibility import identities
    from davinci.product.tasks import template_config

    config, task = engine.validate(yaml.safe_dump(template_config("sensor")))
    first = identities(task, config, IMAGE)
    changed = {**task, "source": task["source"] + "\n# edited builder\n", "version": "changed"}
    assert identities(changed, config, IMAGE) == first


def test_design_schema_cannot_resolve_external_resources():
    p = plan().model_dump()
    p["design_schema"]["properties"]["thickness"] = {"$ref": "https://untrusted.invalid/schema"}
    with pytest.raises(ValueError, match="local JSON pointers"):
        Plan.model_validate(p)


def test_finalization_checks_reference_evidence_integrity(engine):
    row = evaluated(engine, frozen(engine))
    row = engine.lifecycle.reflect(row["_id"], cmd(row, "reflect"), lesson="Measured reference comparison")
    artifact = engine.store.get("artifacts", row["suite_artifact"])
    (engine.artifacts.root / artifact["sha256"]).write_bytes(b"corrupt suite")
    with pytest.raises(ValueError, match="checksum"):
        engine.lifecycle.finalize(row["_id"], cmd(row, "finalize"))
    assert engine.lifecycle.get(row["_id"])["phase"] != "completed"


def test_recovery_preserves_cancellation(engine):
    row = frozen(engine)
    row = engine.lifecycle.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())
    engine.store.update(
        "runs", row["_id"], {"phase": "cancelled", "job": {"id": "interrupted-cancel", "status": "running"}}
    )
    engine.recover()
    row = engine.lifecycle.get(row["_id"])
    assert row["phase"] == "cancelled" and row["job"]["reason"] == "cancelled"


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "1.0"])
def test_measurements_reject_nonfinite_or_coerced_values(value):
    from davinci.product.contracts import Measurement

    with pytest.raises(ValueError):
        Measurement(value=value, unit="g", numerical_error=0, uncertainty=0)
