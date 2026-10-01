"""Shared adapter/evidence checks use deterministic runtime fixtures, never providers."""

import copy
import io
import json

import pytest
from test_lifecycle import EVALUATOR, IMAGE, FixtureRunner, candidate, cmd, opened, plan, verification

from davinci.artifacts import Artifacts
from davinci.config import Settings
from davinci.product.adapters import assess, catalog
from davinci.product.contracts import Evaluator, Plan, Runtime
from davinci.product.engine import Engine
from davinci.product.evidence import archive, manifest
from davinci.product.execution import evaluate_test
from davinci.product.regions import bind_regions
from davinci.product.units import convert, validate_plan_units
from davinci.runner import SandboxError
from davinci.store import Store


def scoped_plan():
    data = plan().model_dump()
    data["tests"][0]["simulation"] = {
        "adapter": "authored-screen",
        "phenomena": ["mass", "linear_static"],
        "material_model": "linear_isotropic",
        "fidelity": "analytic_screen",
        "geometry_assumptions": "40 by 20 mm rectangular cantilever, thickness 1..10 mm",
        "solver_length_unit": "m",
    }
    data["interfaces"][0]["region"] = {
        "center": [-20, 0, 0],
        "normal": [-1, 0, 0],
        "center_tolerance": [0.00001] * 3,
        "extent_min": [0, 20, 1],
        "extent_max": [0.00001, 20, 10],
    }
    return Plan.model_validate(data)


class SimulationRunner(FixtureRunner):
    capacity = {
        "available": True,
        "software": {"cadquery": "2.6.1", "numpy": "2.2.5"},
        "cpu_cores": 2,
        "memory_bytes": 4 * 1024**3,
        "disk_bytes": 1024**3,
    }
    fail = None

    def probe(self, runtime):
        return copy.deepcopy(self.capacity)

    def execute(self, entry, files, **kwargs):
        if self.cancelled():
            raise SandboxError(
                "Cancelled",
                reason="cancelled",
                outputs={"partial.csv": b"x,y\n0,1"},
                log="stopped",
                duration=0.3,
            )
        if entry == "/input/_regions.py":
            t = float(files["model.step"])
            return (
                {
                    "solver.step": b"converted STEP",
                    "faces.json": json.dumps(
                        [
                            {
                                "kind": "PLANE",
                                "center": [-20, 0, 0],
                                "normal": [-1, 0, 0],
                                "extent": [0, 20, t],
                                "area": 20 * t,
                            }
                        ]
                    ).encode(),
                },
                "independent geometry fixture",
                0.1,
            )
        if entry == "/input/_evaluate.py" and self.fail:
            raise SandboxError(
                "Solver stopped",
                reason=self.fail,
                outputs={"partial.csv": b"x,y\n0,1"},
                log="retained solver failure",
                duration=0.2,
            )
        return super().execute(entry, files, **kwargs)


def runtime():
    return Runtime(image=IMAGE, solver="fixture", provenance="deterministic tests")


def test_dimensions_and_explicit_cad_conversion():
    assert convert(1000, "mm", "m", "length") == 1
    assert convert(1, "g/mm3", "kg/m3", "density") == 1_000_000
    assert convert(70, "GPa", "MPa", "pressure") == 70_000
    with pytest.raises(ValueError):
        convert(1, "N", "mm")
    p = scoped_plan()
    validate_plan_units(p)
    p.materials[0].properties["youngs"].unit = "N"
    with pytest.raises(ValueError):
        validate_plan_units(p)


@pytest.mark.parametrize(
    "change,reason",
    [
        ("physics", "unsupported_physics"),
        ("material", "unsupported_material"),
        ("solver", "missing_solver"),
        ("memory", "resource_exhaustion"),
        ("cpu", "resource_exhaustion"),
        ("disk", "resource_exhaustion"),
        ("backend", "unavailable_runtime"),
        ("units", "invalid_units"),
    ],
)
def test_experiment_specific_capabilities(change, reason):
    p, r, runner = scoped_plan(), runtime(), SimulationRunner()
    runner.capacity = copy.deepcopy(runner.capacity)
    if change == "physics":
        p.tests[0].simulation.phenomena = ["nonlinear_contact"]
    if change == "material":
        p.tests[0].simulation.material_model = "plasticity"
    if change == "solver":
        runner.capacity["software"]["numpy"] = None
    if change == "memory":
        runner.capacity["memory_bytes"] = 0
    if change == "cpu":
        runner.capacity["cpu_cores"] = 0.1
    if change == "disk":
        runner.capacity["disk_bytes"] = 10
    if change == "backend":
        r.backend = "remote"
    if change == "units":
        p.tests[0].simulation.cad_unit = "N"
    report = assess(runner, p, p.tests[0], r)
    assert not report["available"]
    assert reason in [i["reason"] for i in report["issues"]]
    assert report["requirements"] == ["strength"] and not report["substitution_performed"]
    result, _, _, _ = evaluate_test(
        runner, b"4", p, p.tests[0], Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="fixture"), r
    )
    assert result.status not in ("pass", "physical_failure")


def test_region_binding_checks_all_geometry_and_ambiguity():
    p = scoped_plan()
    face = {"kind": "PLANE", "center": [-20, 0, 0], "normal": [-1, 0, 0], "extent": [0, 20, 4]}
    assert bind_regions(p.interfaces, [face])[0] == {"root": True}
    for faces in (
        [],
        [face, face],
        [{**face, "center": [20, 0, 0]}],
        [{**face, "normal": [1, 0, 0]}],
        [{**face, "extent": [0, 20, 20]}],
    ):
        assert bind_regions(p.interfaces, faces)[0] == {"root": False}
    # Face indices/labels and candidate hints have no role in matching.
    assert bind_regions(p.interfaces, [{**face, "label": "wrong", "index": 999}])[0]["root"]


@pytest.mark.parametrize("driver", ["external", "managed"])
def test_both_drivers_use_same_adapter_and_manifest(tmp_path, monkeypatch, driver):
    def forbidden(*args, **kwargs):
        raise AssertionError("No generation provider in simulation operations")

    monkeypatch.setenv("OPENAI_API_KEY", "unused-dummy")
    engine = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, mongodb_uri=""),
        provider=forbidden,
        runner=SimulationRunner(),
    )
    life = engine.lifecycle
    row = opened(engine, driver)
    p = scoped_plan()
    row = life.update_plan(
        row["_id"],
        cmd(row, "plan"),
        p,
        Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="fixture"),
        runtime(),
    )
    for t in (4, 2):
        row = life.fixture(row["_id"], cmd(row, f"fixture{t}"), step=str(t).encode(), provenance="reference")
        row = life.verify(row["_id"], cmd(row, f"verify{t}"), verification(row, t))
        assert row["verifications"][-1]["matched"]
    row = life.freeze(row["_id"], cmd(row, "freeze"))
    row = life.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())
    row = life.request_evaluation(row["_id"], cmd(row, "evaluate"))
    result = row["results"][-1]
    assert result["design_accepted"]
    assert result["manifest"]["provenance"]["suite_id"] == row["suite_id"]
    assert {"cad", "bindings", "log", "resources", "result"} <= {
        e["kind"] for e in result["manifest"]["entries"]
    }
    assert result["tests"][0]["metadata"]["cad_to_solver_scale"] == 0.001
    # Final checking must not let an absent final test or a downgraded screen win.
    missing = {**result, "tests": []}
    assert not life._decision(row, missing)["design_accepted"]
    downgraded = copy.deepcopy(result)
    downgraded["tests"][0]["metadata"]["stage"] = "preliminary"
    assert not life._decision(row, downgraded)["evidence_complete"]
    row = life.reflect(row["_id"], cmd(row, "reflect"), lesson="Screen only")
    # Artifact corruption is rejected before acceptance/report export.
    entry = result["manifest"]["entries"][0]
    (engine.artifacts.root / entry["sha256"]).write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        life.finalize(row["_id"], cmd(row, "finalize"))


@pytest.mark.parametrize("reason", ["cancelled", "timeout", "resource_exhaustion", "artifact_quota"])
def test_typed_failure_preserves_partial_artifacts(reason):
    p, runner = scoped_plan(), SimulationRunner()
    runner.fail = reason
    result, outputs, log, seconds = evaluate_test(
        runner,
        b"4",
        p,
        p.tests[0],
        Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="fixture"),
        runtime(),
    )
    assert result.status == "not_run" and result.reason == reason
    assert outputs["partial.csv"] and "retained solver failure" in log and seconds >= 0.2


def test_prescribed_final_evidence_not_replaced_by_screen():
    p = scoped_plan()
    p.tests[0].simulation.required_evidence = ["convergence", "fields"]
    result, _, _, _ = evaluate_test(
        SimulationRunner(),
        b"4",
        p,
        p.tests[0],
        Evaluator(resources={"evaluate.py": EVALUATOR}, provenance="fixture"),
        runtime(),
    )
    assert result.reason == "missing_evidence"


def test_bounded_artifacts_and_stream_integrity(tmp_path):
    store = Store(tmp_path)
    artifacts = Artifacts(tmp_path, store)
    with pytest.raises(ValueError, match="quota"):
        artifacts.put_stream(io.BytesIO(b"x" * 2048), "field.vtk", "application/octet-stream", max_bytes=1024)
    for name in ("../data", "/absolute", "nested/file", "bad\\path"):
        with pytest.raises(ValueError):
            artifacts.put(b"no", name, "text/plain")
    identity = artifacts.put_stream(io.BytesIO(b"x" * 2_000_000), "field.vtk", "application/octet-stream")
    with artifacts.verified_open(identity) as stream:
        assert sum(len(c) for c in artifacts.chunks(stream)) == 2_000_000
    record = store.get("artifacts", identity)
    path = artifacts.root / record["sha256"]
    path.unlink()
    path.symlink_to("/etc/hostname")
    with pytest.raises(ValueError):
        artifacts.read(identity)
    refs = archive(artifacts, {"evil.html": b"<script>bad</script>", "execution.log": b"good"}, "")
    m = manifest(artifacts, refs, {"test_id": "test"})
    assert not m.complete and "evil.html" in m.omissions
    assert {a["id"] for a in catalog()} == {
        "sensor-screen",
        "gripper-screen",
        "vtol-screen",
        "authored-screen",
    }


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires local CAD Docker image"
)
@pytest.mark.parametrize("driver", ["external", "managed"])
def test_native_scoped_adapter_and_independent_regions(tmp_path, driver):
    import subprocess

    from davinci.product.execution import build
    from davinci.runner import Runner

    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    r = runtime().model_copy(update={"image": image})
    p = scoped_plan()
    evaluator = Evaluator(
        resources={"evaluate.py": EVALUATOR}, provenance="analytical Euler-Bernoulli reference"
    )
    # Driver identity is independent of physics; neither external nor managed evaluation invokes a provider.
    engine = Engine(
        tmp_path / "workspace",
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
        runner=runner,
    )
    row = opened(engine, driver)
    row = engine.lifecycle.update_plan(row["_id"], cmd(row, "plan"), p, evaluator, r)
    for t in (4, 2):
        step, _, _ = build(runner, candidate(t), p, r)
        result, outputs, _, _ = evaluate_test(runner, step, p, p.tests[0], evaluator, r)
        assert result.status == ("pass" if t == 4 else "physical_failure"), result
        assert json.loads(outputs["bindings.json"])["root"]["observed_count"] == 1
        assert result.metrics["stress_mpa"].value == pytest.approx(6 * 100 * 40 / (20 * t * t))
        # Native OCP import verifies the explicitly converted solver geometry in metres.
        check = "import cadquery as cq\nfrom pathlib import Path\ns=cq.importers.importStep('/input/solver.step').val()\nPath('/output/width.txt').write_text(str(s.BoundingBox().xlen))"
        measured, _, _ = runner.execute(
            "/input/check.py", {"check.py": check, "solver.step": outputs["prepare-solver.step"]}, image=image
        )
        assert float(measured["width.txt"]) == pytest.approx(0.04)
        row = engine.lifecycle.fixture(
            row["_id"], cmd(row, f"fixture{t}"), step=step, provenance="rectangular reference"
        )
        row = engine.lifecycle.verify(row["_id"], cmd(row, f"verify{t}"), verification(row, t))
        assert row["verifications"][-1]["matched"]
    row = engine.lifecycle.freeze(row["_id"], cmd(row, "freeze"))
    row = engine.lifecycle.submit_candidate(row["_id"], cmd(row, "candidate"), candidate())
    row = engine.lifecycle.request_evaluation(row["_id"], cmd(row, "evaluate"))
    assert row["results"][-1]["design_accepted"]
    duplicate = candidate()
    duplicate.source = duplicate.source.replace(
        "return cq.Assembly(model)", "return cq.Assembly().add(model, name='a').add(model, name='b')"
    )
    ambiguous_step, _, _ = build(runner, duplicate, p, r)
    ambiguous, _, _, _ = evaluate_test(runner, ambiguous_step, p, p.tests[0], evaluator, r)
    assert ambiguous.reason == "invalid_binding"
    p.interfaces[0].region.center = (999, 0, 0)
    invalid, _, _, _ = evaluate_test(runner, step, p, p.tests[0], evaluator, r)
    assert invalid.reason == "invalid_binding"


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires local CAD Docker image"
)
def test_native_failure_outputs_and_budget(tmp_path):
    import subprocess

    from davinci.runner import Runner

    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    script = "from pathlib import Path\nimport time\nPath('/output/partial.csv').write_text('x,y\\n0,1')\nprint('solver started', flush=True)\ntime.sleep(10)"
    with pytest.raises(SandboxError) as failure:
        runner.execute("/input/run.py", {"run.py": script}, timeout=2, image=image)
    assert failure.value.reason == "timeout"
    assert failure.value.outputs["partial.csv"]
    assert "solver started" in failure.value.log
    assert json.loads(failure.value.outputs["resources.json"])["wall_seconds"] >= 2
    import time

    deadline = time.monotonic() + 2
    runner.cancelled = lambda: time.monotonic() >= deadline
    with pytest.raises(SandboxError) as stopped:
        runner.execute("/input/run.py", {"run.py": script}, timeout=20, image=image)
    assert stopped.value.reason == "cancelled" and stopped.value.outputs["partial.csv"]
    runner.cancelled = lambda: False
    script = "from pathlib import Path\nfor n in range(20):\n Path('/output/field'+str(n)+'.csv').write_bytes(b'x'*1000)"
    with pytest.raises(SandboxError) as failure:
        runner.execute("/input/run.py", {"run.py": script}, image=image, artifact_bytes=2048)
    assert failure.value.reason == "artifact_quota"


def test_measurement_conversion_includes_accuracy_bounds():
    from davinci.product.execution import score

    p = scoped_plan()
    out, _, _ = SimulationRunner().execute(
        "/input/_evaluate.py",
        {"model.step": b"4", "request.json": json.dumps({"test": p.tests[0].model_dump()})},
    )
    raw = json.loads(out["result.json"])
    for key in ("value", "numerical_error", "uncertainty"):
        raw["metrics"]["mass_g"][key] /= 1000
    raw["metrics"]["mass_g"]["unit"] = "kg"
    result = score(p.tests[0], p, raw)
    assert result.status == "pass"
    assert result.metrics["mass_g"].value == pytest.approx(8.64)
    assert result.metrics["mass_g"].numerical_error == pytest.approx(0.00001)
    raw["metrics"]["mass_g"]["unit"] = "N"
    assert score(p.tests[0], p, raw).reason == "invalid_units"
    # Compatibility plans keep exact strings; they are never silently converted.
    raw["metrics"]["mass_g"]["unit"] = "kg"
    legacy = plan()
    assert score(legacy.tests[0], legacy, raw).reason == "invalid_result"


def test_total_job_budget_stops_remaining_tests(tmp_path):
    from test_lifecycle import evaluated, frozen

    class SlowFixture(FixtureRunner):
        def execute(self, entry, files, **kwargs):
            out, log, seconds = super().execute(entry, files, **kwargs)
            return out, log, 4000 if entry.endswith("_build.py") else seconds

    engine = Engine(
        tmp_path,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        runner=SlowFixture(),
    )
    row = evaluated(engine, frozen(engine))
    result = row["results"][-1]
    assert not result["design_accepted"] and not result["evidence_complete"]
    assert result["tests"][0]["reason"] == "resource_exhaustion"
    assert result["artifacts"]["model.step"]
