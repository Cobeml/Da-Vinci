"""Optional static-solid contracts and actual Gmsh/CalculiX references. No paid models."""

import json
import os
import subprocess
import time

import pytest

from davinci.config import Settings
from davinci.product.adapters import assess
from davinci.product.contracts import Candidate, Evaluator, Runtime
from davinci.product.execution import build, evaluate_test
from davinci.product.structural.adapter import setup
from davinci.product.structural.examples import beam_reference, bracket_plan, candidate
from davinci.runner import Runner

EVALUATOR = Evaluator(
    resources={
        "evaluate.py": "raise RuntimeError('Authored evaluators cannot override trusted structural measurements')"
    },
    provenance="Host-owned calculix-static adapter; no authored implementation executes",
)


def runtime():
    try:
        image = subprocess.check_output(
            ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-structural:local"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        pytest.fail("Required optional structural image unavailable. Run davinci setup --template structural")
    return Runtime(
        image=image,
        solver="Gmsh 4.15.2 + CalculiX 2.23",
        provenance="Local source-pinned structural test runtime",
        timeout_seconds=300,
        cpu_cores=1,
        memory_gb=4,
        artifact_bytes=200_000_000,
        file_bytes=64_000_000,
    )


def test_structural_setup_contract():
    p = bracket_plan()
    normalized = setup(p, p.tests[0])
    assert normalized["material"]["density_g_mm3"] == 0.0027
    assert normalized["force_n"] == [0, 0, -20]
    p.tests[0].load_cases[0].quantities["force_x"].unit = "mm"
    with pytest.raises(ValueError, match="dimension"):
        setup(p, p.tests[0])


@pytest.mark.parametrize(
    "change,reason",
    [
        ("physics", "unsupported_physics"),
        ("material", "unsupported_material"),
        ("solver", "missing_solver"),
        ("capacity", "resource_exhaustion"),
    ],
)
def test_structural_capabilities(change, reason):
    class Probe:
        def probe(self, runtime):
            return {
                "available": True,
                "software": {"cadquery": "2.6.1", "numpy": "2.2.5", "gmsh": "4.15.2", "calculix": "2.23"},
                "memory_bytes": 4 * 1024**3,
            }

    p = bracket_plan()
    test = p.tests[0]
    r = Runtime(image="sha256:" + "1" * 64, solver="fixture", provenance="No solver executes")
    if change == "physics":
        test.simulation.phenomena.append("fatigue")
    if change == "material":
        test.simulation.material_model = "nonlinear_plastic"
    if change == "solver":
        test.simulation.required_software = {"calculix": "99"}
    if change == "capacity":
        test.simulation.estimate.memory_mb = 99999
    assert reason in {i["reason"] for i in assess(Probe(), p, test, r)["issues"]}


def test_singularity_policy_is_predeclared():
    p = bracket_plan()
    del p.tests[0].fixed_inputs["structural"]["stress_region"]["justification"]
    with pytest.raises(ValueError):
        setup(p, p.tests[0])
    p = bracket_plan()
    p.tests[0].simulation.required_evidence = []
    with pytest.raises(ValueError, match="evidence"):
        setup(p, p.tests[0])


def measure(tmp_path, plan, variant):
    rt = runtime()
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))
    step, _, _ = build(runner, Candidate.model_validate(candidate(variant)), plan, rt)
    result, outputs, log, _ = evaluate_test(runner, step, plan, plan.tests[0], EVALUATOR, rt)
    folder = tmp_path / variant
    folder.mkdir(exist_ok=True)
    for name, data in outputs.items():
        (folder / name).write_bytes(data)
    (folder / "result-summary.json").write_text(result.model_dump_json(indent=2))
    assert result.status in ("pass", "physical_failure"), result.model_dump()
    convergence = json.loads(outputs["convergence.json"])
    assert convergence["converged"] and len(convergence["levels"]) >= 3
    assert max(level["reaction_relative_residual"] for level in convergence["levels"]) < 0.001
    assert max(level["moment_relative_residual"] for level in convergence["levels"]) < 0.001
    return result, outputs


native = pytest.mark.skipif(
    os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Explicit optional solver integration opt-in"
)


@pytest.mark.integration
@native
def test_native_structural_uniaxial_reference(tmp_path):
    p = bracket_plan()
    p.materials[0].properties["poisson_ratio"].value = 0.0
    load = p.tests[0].load_cases[0].quantities
    load["force_x"].value = 1000.0
    load["force_z"].value = 0.0
    result, _ = measure(tmp_path, p, "beam-thick")
    assert result.status == "pass"
    assert result.metrics["load_displacement_mm"].value == pytest.approx(1000 * 60 / (70000 * 160), rel=0.001)
    assert result.metrics["gauge_von_mises_mpa"].value == pytest.approx(1000 / 160, rel=0.001)
    assert result.metrics["mass_g"].value == pytest.approx(60 * 20 * 8 * 0.0027, rel=1e-7)


@pytest.mark.integration
@native
@pytest.mark.parametrize(
    "variant,thickness,status", [("beam-thin", 4, "physical_failure"), ("beam-thick", 8, "pass")]
)
def test_native_structural_beam_reference(tmp_path, variant, thickness, status):
    result, _ = measure(tmp_path, bracket_plan(), variant)
    assert result.status == status
    reference = beam_reference(thickness)
    assert result.metrics["load_displacement_mm"].value == pytest.approx(
        reference["load_displacement_mm"], rel=0.06
    )
    assert result.metrics["gauge_von_mises_mpa"].value == pytest.approx(
        reference["gauge_von_mises_mpa"], rel=0.15
    )


@pytest.mark.integration
@native
def test_native_structural_bracket_revision(tmp_path):
    base, _ = measure(tmp_path, bracket_plan(), "bracket-base")
    improved, _ = measure(tmp_path, bracket_plan(), "bracket-ribbed")
    assert base.status == "physical_failure" and improved.status == "pass"
    assert improved.metrics["load_displacement_mm"].value < base.metrics["load_displacement_mm"].value * 0.7


@pytest.mark.integration
@native
@pytest.mark.parametrize(
    "case,expected",
    [
        ("disconnected", "invalid_setup"),
        ("reversed-normal", "invalid_setup"),
        ("gauge-at-clamp", "invalid_setup"),
        ("mesh-budget", "not_run"),
        ("unconverged", "numerical_failure"),
    ],
)
def test_native_structural_invalid_and_incomplete(tmp_path, case, expected):
    plan = bracket_plan()
    variant = "disconnected" if case == "disconnected" else "beam-thick"
    if case == "reversed-normal":
        plan.interfaces[0].region.normal = (1.0, 0.0, 0.0)
    if case == "gauge-at-clamp":
        plan.tests[0].fixed_inputs["structural"]["stress_region"]["lower_mm"] = [0, -10, 0]
    if case == "mesh-budget":
        plan.tests[0].fixed_inputs["structural"]["mesh"]["max_nodes"] = 10
    if case == "unconverged":
        plan.tests[0].fixed_inputs["structural"]["mesh"].update(max_levels=3, relative_tolerance=1e-10)
    rt = runtime()
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))
    step, _, _ = build(runner, Candidate.model_validate(candidate(variant)), plan, rt)
    result, outputs, _, _ = evaluate_test(runner, step, plan, plan.tests[0], EVALUATOR, rt)
    assert result.status == expected, result.model_dump()
    assert not result.applicable and result.status != "pass"
    if case not in ("disconnected", "reversed-normal"):
        assert any(k.endswith(".msh") for k in outputs)


@pytest.mark.integration
@native
def test_native_structural_public_driver_parity(tmp_path):
    from fastapi.testclient import TestClient

    from davinci.product.api import create_app
    from davinci.product.client import Client
    from davinci.product.engine import Engine
    from davinci.product.structural.walkthrough import author, plan_bundle

    rt = runtime()
    calls = []

    class ReasoningFixture:
        def __init__(self, engine, row):
            assert row["driver"] == "managed", "External route must not instantiate any provider"

        def request(self, key, instruction, context):
            calls.append(key)
            if context.get("stage") == "propose":
                return candidate("bracket-ribbed")
            if context.get("stage") == "diagnose":
                return {
                    "lesson": "Hypothesis: ribs reduce compliance under the unchanged suite",
                    "action": "design",
                    "explanation": "Use actual measured failure and retain every fixed test",
                }
            if "lifecycle-author" in key:
                return plan_bundle(rt.image)
            if "lifecycle-propose" in key:
                return candidate("bracket-base" if not context["candidates"] else "bracket-ribbed")
            if "lifecycle-reflect" in key:
                return {
                    "lesson": "Hypothesis: tapered ribs redistribute material to stiffen the shelf; retain measured failures and frozen constraints."
                }
            raise AssertionError(key)

    engine = Engine(
        tmp_path,
        provider=ReasoningFixture,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key="dummy-key-must-not-be-used"),
    )
    outcomes, experiments = {}, {}
    with TestClient(create_app(tmp_path, engine=engine)) as http:

        class PublicClient(Client):
            def request(self, method, path, body=None, *, binary=False):
                r = http.request(method, path, json=body)
                assert r.status_code < 300, r.text
                return r.content if binary else r.json()

        client = PublicClient(tmp_path)
        for driver in ("external", "managed"):
            row = author(
                client,
                driver=driver,
                operation="structural-" + driver,
                mode="live" if driver == "external" else "replay",
            )
            eid = row["_id"]
            suite = row["suite_id"]

            def post(action, payload, op):
                row = client.status(eid)
                return client.request(
                    "POST",
                    f"/api/v2/experiments/{eid}/{action}",
                    {"actor": row["actor"], "revision": row["revision"], "operation_id": op, **payload},
                )

            measured = []
            for index, variant in enumerate(("bracket-base", "bracket-ribbed")):
                if driver == "managed":
                    post("managed/propose", {}, f"propose-{index}")
                else:
                    post("candidates", {"candidate": candidate(variant)}, f"candidate-{index}")
                job = post("evaluate", {}, f"evaluate-{index}")
                done = client.wait(eid, job["id"], 900)
                assert done["status"] == "completed", done
                row = client.status(eid)
                result = row["results"][-1]
                assert result["evidence_complete"] and result["design_accepted"] == (index == 1), result
                assert row["suite_id"] == suite
                assert result["manifest"]["complete"]
                if driver == "managed":
                    post("managed/reflect", {}, f"reflect-{index}")
                else:
                    post(
                        "reflections",
                        {
                            "result_id": result["id"],
                            "lesson": "External hypothesis recorded with independently measured evidence",
                        },
                        f"reflect-{index}",
                    )
                measured.append(result)
            post("finalize", {}, "finalize")
            assert client.request("GET", f"/api/v2/experiments/{eid}/report")["report"][
                "accepted_candidate_ids"
            ]
            outcomes[driver] = measured
            experiments[driver] = client.status(eid)
            if driver == "external":
                assert not calls
        for a, b in zip(outcomes["external"], outcomes["managed"]):
            # Independently frozen suites retain distinct reference/probe provenance.
            for field in ("plan_id", "candidate_version", "runtime_id", "execution_id", "evaluator_id"):
                assert a[field] == b[field]
            for metric, m in a["tests"][0]["metrics"].items():
                assert m["value"] == pytest.approx(
                    b["tests"][0]["metrics"][metric]["value"], rel=1e-8, abs=1e-7
                )
        assert len(calls) == 5
        # Exact suite parity via supported continuation: no copied scores; automatic managed
        # adoption evaluates the failing seed, revises it, and reruns the final required suite.
        parent = experiments["external"]
        adopted = client.request(
            "POST",
            f"/api/v2/experiments/{parent['_id']}/continue",
            {
                "actor": parent["actor"],
                "revision": parent["revision"],
                "operation_id": "adopt-structural",
                "candidate_id": parent["candidates"][0]["id"],
                "driver": "managed",
                "new_actor": "fixture-managed",
                "policy": {"max_candidates": 2, "min_candidates": 2},
            },
        )
        assert not adopted["results"]
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            adopted = client.status(adopted["_id"])
            if adopted["managed"]["status"] != "ready":
                break
            time.sleep(0.1)
        assert adopted["managed"]["status"] == "completed", adopted["managed"]
        assert len(adopted["results"]) == 3 and adopted["report"]["accepted_candidate_ids"]
        for a, b in zip(outcomes["external"], adopted["results"][:2]):
            for field in ("suite_id", "candidate_version", "runtime_id", "execution_id", "evaluator_id"):
                assert a[field] == b[field]
            for metric, m in a["tests"][0]["metrics"].items():
                assert m["value"] == pytest.approx(
                    b["tests"][0]["metrics"][metric]["value"], rel=1e-8, abs=1e-7
                )
        outcomes["managed_adoption"] = adopted["results"]
        (tmp_path / "parity-summary.json").write_text(json.dumps(outcomes, indent=2))


@pytest.mark.integration
@native
def test_native_structural_uses_exported_geometry_not_claims(tmp_path):
    plan = bracket_plan()
    rt = runtime()
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))
    proposed = candidate("beam-thick")
    proposed["metadata"] = {"claimed_volume_mm3": 9600, "claimed_thickness_mm": 8}
    proposed["source"] = proposed["source"].replace(
        "thickness = 4 if variant == 'beam-thin' else 8", "thickness = 4"
    )
    step, _, _ = build(runner, Candidate.model_validate(proposed), plan, rt)
    result, outputs, _, _ = evaluate_test(runner, step, plan, plan.tests[0], EVALUATOR, rt)
    assert result.status == "physical_failure", result.model_dump()
    assert result.metrics["mass_g"].value == pytest.approx(60 * 20 * 4 * 0.0027, rel=1e-7)
    assert result.metrics["load_displacement_mm"].value > 0.1
    assert json.loads(outputs["prepare-geometry.json"])["volume"] == pytest.approx(4800)
