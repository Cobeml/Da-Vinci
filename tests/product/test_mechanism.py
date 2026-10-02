"""MuJoCo optional native checks, never paid generation. Fixtures are explicitly synthetic CAD."""

import json
import os
import subprocess

import pytest

from davinci.config import Settings
from davinci.product.adapters import assess
from davinci.product.contracts import Candidate, Evaluator, Runtime
from davinci.product.execution import build, evaluate_test
from davinci.product.mechanism.adapter import setup
from davinci.product.mechanism.examples import bundle, candidate, plan
from davinci.runner import Runner


def runtime():
    try:
        image = subprocess.check_output(
            ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-mujoco:local"],
            text=True,
            stderr=subprocess.PIPE,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        pytest.fail("Required MuJoCo image unavailable: davinci setup --template mujoco")
    return Runtime.model_validate(bundle(image)["runtime"])


def test_mechanism_contract():
    p = plan()
    normalized = setup(p, p.tests[0])
    assert normalized["density_kg_m3"]["aluminium"] == 2700
    p.tests[0].load_cases[0].quantities["gravity"].unit = "mm"
    with pytest.raises(ValueError):
        setup(p, p.tests[0])


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("physics", "unsupported_physics"),
        ("solver", "missing_solver"),
        ("resources", "resource_exhaustion"),
        ("accelerator", "unsupported_physics"),
        ("binding", "invalid_binding"),
    ],
)
def test_mechanism_capabilities(problem, reason):
    class Probe:
        def probe(self, runtime):
            return dict(
                available=True,
                software={"cadquery": "2.6.1", "numpy": "2.2.5", "mujoco": "3.4.0"},
                memory_bytes=4 * 1024**3,
            )

    p = plan()
    t = p.tests[0]
    r = Runtime(image="sha256:" + "1" * 64, solver="fixture", provenance="No physics execution", memory_gb=2)
    if problem == "physics":
        t.simulation.phenomena.append("fatigue")
    if problem == "solver":
        t.simulation.required_software["mujoco"] = "99"
    if problem == "resources":
        r.memory_gb = 0.1
    if problem == "accelerator":
        r.accelerator = "cuda"
    if problem == "binding":
        p.interfaces[1].region.normal = (1, 0, 0)
    assert reason in {v["reason"] for v in assess(Probe(), p, t, r)["issues"]}


native = pytest.mark.skipif(
    os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Explicit optional MuJoCo integration opt-in"
)


def measure(root, variant):
    r = runtime()
    p = plan()
    runner = Runner(Settings(_env_file=None, davinci_data_dir=root, openai_api_key="", mongodb_uri=""))
    step, _, _ = build(runner, Candidate.model_validate(candidate(variant)), p, r)
    result, outputs, log, _ = evaluate_test(
        runner, step, p, p.tests[0], Evaluator.model_validate(bundle(r.image)["evaluator"]), r
    )
    folder = root / variant
    folder.mkdir(exist_ok=True, parents=True)
    for name, data in outputs.items():
        (folder / name).write_bytes(data)
    (folder / "execution.log").write_text(log)
    return result, outputs


@native
@pytest.mark.integration
@pytest.mark.parametrize(
    "variant,status",
    [
        ("solid", "physical_failure"),
        ("reference-light", "pass"),
        ("pocketed", "pass"),
        ("misplaced", "invalid_setup"),
        ("ambiguous", "invalid_setup"),
    ],
)
def test_native_mechanism_cases(tmp_path, variant, status):
    result, outputs = measure(tmp_path, variant)
    assert result.status == status, result.model_dump()
    if status == "invalid_setup":
        assert result.reason == "invalid_binding"
        return
    bodies = json.loads(outputs["assembly-bindings.json"])
    car = bodies["carriage"]
    h = 6 if variant == "reference-light" else 20
    d = 18 if variant == "pocketed" else 0
    # Independent nominal box subtraction, not CAD supplied volume/thickness.
    volume = 40 * 30 * h - 32 * 22 * d
    assert car["mass_kg"] == pytest.approx(volume * 2700e-9, rel=1e-9)
    outer_mass = 40 * 30 * h * 2700e-9
    hole_mass = 32 * 22 * d * 2700e-9
    com = ((20 + h / 2) * outer_mass - (20 + h - d / 2) * hole_mass) / (outer_mass - hole_mass) * 0.001
    assert car["com_m"][2] == pytest.approx(com, abs=1e-10)

    def inertia(m, x, y, z):
        return [m * (y * y + z * z) / 12, m * (x * x + z * z) / 12, m * (x * x + y * y) / 12]

    a = inertia(outer_mass, 0.04, 0.03, h * 0.001)
    b = inertia(hole_mass, 0.032, 0.022, d * 0.001)
    shifts = [
        outer_mass * ((20 + h / 2) * 0.001 - com) ** 2 - hole_mass * ((20 + h - d / 2) * 0.001 - com) ** 2
    ] * 2 + [0]
    for i in range(3):
        assert car["inertia_kg_m2"][i][i] == pytest.approx(a[i] - b[i] + shifts[i], rel=1e-8)
    assert json.loads(outputs["convergence.json"])["converged"]
    refs = json.loads(outputs["reference-checks.json"])
    assert refs["force_motion"]["error_m"] <= refs["force_motion"]["tolerance_m"]
    assert "mechanism-2.xml" in outputs and "settle-2.csv" in outputs


@native
@pytest.mark.integration
def test_native_mechanism_unconverged(tmp_path):
    p = plan()
    p.tests[0].fixed_inputs["mechanism"]["timestep_seconds"] = 0.001
    # Keep the original strict trajectory limit: this coarse contact integration is inadequate.
    r = runtime()
    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, openai_api_key="", mongodb_uri=""))
    step, _, _ = build(runner, Candidate.model_validate(candidate("solid")), p, r)
    result, outputs, _, _ = evaluate_test(
        runner, step, p, p.tests[0], Evaluator.model_validate(bundle(r.image)["evaluator"]), r
    )
    assert result.status == "numerical_failure"
    assert not json.loads(outputs["convergence.json"])["converged"]
    assert "settle-0.csv" in outputs and "solver-resources.json" in outputs


@native
@pytest.mark.integration
def test_native_mechanism_public_routes(tmp_path):
    from fastapi.testclient import TestClient

    from davinci.product.api import create_app
    from davinci.product.client import Client, ClientError
    from davinci.product.engine import Engine
    from davinci.product.mechanism.walkthrough import MechanismBenchmark, MechanismProvider

    runtime()  # Fail clearly if the expected optional image is missing.
    engine = Engine(
        tmp_path,
        provider=MechanismProvider,
        credentials=Settings(_env_file=None, openai_api_key="unused-present-key", mongodb_uri=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as http:

        class Public(Client):
            def request(self, method, path, body=None, **kwargs):
                response = http.request(method, path, json=body)
                if response.status_code >= 300:
                    raise ClientError(str(response.json()), {409: 4, 422: 2}.get(response.status_code, 1))
                return response.json()

        client = Public(tmp_path)
        results = [MechanismBenchmark(client, d, tmp_path / d).run() for d in ("external", "managed")]
        a, b = [v["cases"][0] for v in results]
        assert a["acceptance_contract_id"] == b["acceptance_contract_id"]
        for k, v in a["final_metrics"].items():
            assert v["value"] == pytest.approx(b["final_metrics"][k]["value"], rel=1e-8, abs=1e-8)
        assert not engine.store.list("requests")  # Fixture never makes a model/API request.
        (tmp_path / "mechanism-parity.json").write_text(json.dumps(results, indent=2))
