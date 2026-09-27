import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sandbox"))
from vtol_family import BASELINE, validate  # noqa: E402
from vtol_physics import Polars, Props, beam, mass_properties, tube  # noqa: E402
from vtol_spec import SPECIFICATION as S  # noqa: E402


def test_prop_maps_and_domain():
    p = Props()
    row = p.static[8]
    rpm, ct, cp = row
    d = S["lift_prop_diameter_m"]
    n = rpm / 60
    force = ct * S["rho"] * n * n * d**4
    power, capacity = p.hover(force)
    expected = cp * S["rho"] * n**3 * d**5 / (S["motor_efficiency"] * S["esc_efficiency"])
    assert power == pytest.approx(expected, rel=0.002)
    assert capacity > force
    assert p.hover(capacity * 1.1)[0] is None
    assert p.cruise(40, 2) is None
    assert p.cruise(15, 2)["power_w"] > 30


def test_structure_and_mass_accounting():
    d, t = 0.025, 0.0012
    area, i = tube(d, t)
    assert area > 0 and i > 0
    r = beam(100, 1, d, t)
    assert r["stress_pa"] == pytest.approx(100 * d / (2 * i))
    assert r["deflection_m"] == pytest.approx(100 / (3 * 69e9 * i))
    components = [
        {"name": "battery", "mass_kg": 1, "cg_x_m": 0.2},
        {"name": "payload", "mass_kg": 0.5, "cg_x_m": 0.5},
    ]
    mass, cg = mass_properties(BASELINE, components, payload=0.8)
    assert mass == pytest.approx(1.8)
    assert cg == pytest.approx((0.2 + 0.8 * BASELINE["payload_x"]) / 1.8)


def test_polars_are_converged_and_no_extrapolation():
    p = Polars()
    assert len(p.tables) == 12
    assert all(len(x["rows"]) >= 15 for x in p.tables)
    assert 0.003 < p.drag("2412", 400000, 0.5) < 0.05
    assert p.drag("2412", 50000, 0.5) is None
    assert p.drag("2412", 400000, 5) is None
    with pytest.raises(ValueError):
        validate({**BASELINE, "span": float("nan")})


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires VTOL container")
def test_vtol_baseline_energy_clearance_and_forged_step(tmp_path):
    from davinci.config import Settings
    from davinci.runner import Runner
    from davinci.vtol import REFERENCE_SOURCE, evaluate

    runner = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path))
    e, files = evaluate(runner, REFERENCE_SOURCE, BASELINE)
    assert e["outcome"] == "passed", e["violations"]
    n = e["performance"]["nominal"]
    best = n["best"]
    assert best["range_km"] * best["wh_km"] + n["overhead_wh"] + n["reserve_wh"] == pytest.approx(150)
    assert n["mass_kg"] == pytest.approx(sum(x["mass_kg"] for x in e["components"]))
    assert e["performance"]["scenarios"]["combined_adverse"]["range_km"] < n["range_km"]
    assert e["metrics"]["payload_capacity_kg"]["value"] >= 0.5
    assert files["model.glb"][:4] == b"glTF"
    forged = REFERENCE_SOURCE.replace(
        "return build_vtol(parameters)", "return build_vtol({**parameters, 'span': 1.7})"
    )
    bad, _ = evaluate(runner, forged, BASELINE)
    assert bad["outcome"] == "failed"
    assert any(v["code"] == "UNSUPPORTED_GEOMETRY" for v in bad["violations"])


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires VTOL container")
def test_vlm_lift_slope_and_trim_authority(tmp_path):
    from davinci.config import Settings
    from davinci.runner import Runner
    from davinci.vtol import FILES, SANDBOX

    code = """import json, math
from vtol_family import BASELINE
from vtol_physics import aero_model
x=aero_model(BASELINE,.40)
assert x['cl'][1]>0 and x['cl'][2]>0
assert x['cm'][2]<0
assert 0<x['static_margin']<.5
assert x['cnb_per_deg']>0
import aerosandbox as a
w=a.Wing(symmetric=True,xsecs=[a.WingXSec(xyz_le=[0,0,0],chord=.3,airfoil=a.Airfoil('naca0012')),a.WingXSec(xyz_le=[0,1.05,0],chord=.3,airfoil=a.Airfoil('naca0012'))])
p=a.Airplane(wings=[w])
r=a.VortexLatticeMethod(p,a.OperatingPoint(velocity=20,alpha=3),spanwise_resolution=14,chordwise_resolution=6).run()
analytic=2*math.pi/(1+2/7)*math.radians(3)
assert abs(float(r['CL'])/analytic-1)<.15
assert float(r['CD'])>0
"""
    files = {n: (SANDBOX / n).read_text() for n in FILES}
    files["check.py"] = code
    Runner(Settings(_env_file=None, davinci_data_dir=tmp_path)).execute(
        "/input/check.py", files, image="da-vinci-vtol:local"
    )


def test_weak_structure_and_mission_sensitivity():
    from vtol_physics import structural

    weak = {**BASELINE, "spar_diameter": 0.018, "spar_wall": 0.0008}
    assert not structural(weak, 5, 0.5)["passed"]
    assert structural(BASELINE, 4.47, 0.5)["passed"]


def test_speed_and_payload_protection():
    from scripts.vtol_study import protect

    base = {"metrics": {"max_speed_m_s": {"value": 20}, "payload_capacity_kg": {"value": 1}}}
    candidate = {
        "outcome": "passed",
        "violations": [],
        "metrics": {"max_speed_m_s": {"value": 18}, "payload_capacity_kg": {"value": 0.9}},
    }
    result = protect(candidate, base)
    assert result["outcome"] == "failed"
    assert {x["code"] for x in result["violations"]} == {"SPEED_RETENTION", "PAYLOAD_RETENTION"}
