"""Trusted isolated MuJoCo slider. All geometry/mass/inertia comes from exported STEP."""

import csv
import json
import math
import resource
import time
from pathlib import Path

import cadquery as cq
import mujoco
import numpy as np

OUT = Path("/output")


class Invalid(Exception):
    pass


class Numerical(Exception):
    pass


def write(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False))


def need(ok, message):
    if not ok:
        raise Invalid(message)


def inspect(request):
    solids = cq.importers.importStep("/input/model.step").solids().vals()
    need(
        len(solids) == 2 and all(s.isValid() for s in solids),
        "Exactly two valid separate solid bodies required",
    )
    bodies = {}
    used = []
    for spec in request["mechanism"]["settings"]["bodies"]:
        target = request["validated_bindings"][spec["interface"]]["matches"][0]
        matches = []
        for index, solid in enumerate(solids):
            for face in solid.Faces():
                bb = face.BoundingBox()
                if (
                    face.geomType() == "PLANE"
                    and np.allclose(face.Center().toTuple(), target["center"], atol=1e-5, rtol=0)
                    and np.allclose(face.normalAt().toTuple(), target["normal"], atol=1e-7, rtol=0)
                    and np.allclose([bb.xlen, bb.ylen, bb.zlen], target["extent"], atol=1e-5, rtol=0)
                    and math.isclose(face.Area(), target["area"], rel_tol=1e-8, abs_tol=1e-5)
                ):
                    matches.append(index)
        need(len(matches) == 1, spec["name"] + ": missing/ambiguous solid binding")
        index = matches[0]
        used.append(index)
        solid = solids[index]
        bb = solid.BoundingBox()
        rho = request["mechanism"]["density_kg_m3"][spec["material"]]
        extent = np.array([bb.xlen, bb.ylen, bb.zlen])
        lo = np.array([bb.xmin, bb.ymin, bb.zmin])
        hi = lo + extent
        mass = solid.Volume() * 1e-9 * rho
        inertia = np.array(cq.Shape.matrixOfInertia(solid)) * 1e-15 * rho
        eig = np.linalg.eigvalsh(inertia)
        need(1e-6 < mass < 20 and np.all(eig > 0) and eig[-1] < sum(eig[:2]) + 1e-12, "Invalid mass/inertia")
        need(np.all(extent > 0.5) and np.all(extent < 500), "Validated body extents are .5..500 mm")
        need(
            math.isclose(target["area"], extent[0] * extent[1], rel_tol=1e-7),
            "Stop-contact face must fill rectangular envelope",
        )
        expected_z = hi[2] if spec["role"] == "fixed" else lo[2]
        need(
            abs(target["center"][2] - expected_z) < 1e-5,
            "Selected stop interface is not an extreme horizontal face",
        )
        if spec["role"] == "fixed":
            need(
                math.isclose(solid.Volume(), float(np.prod(extent)), rel_tol=1e-7),
                "Fixed base must fill its box envelope",
            )
        bodies[spec["name"]] = dict(
            mass_kg=mass,
            inertia_kg_m2=inertia.tolist(),
            com_m=(np.array(solid.Center().toTuple()) * 0.001).tolist(),
            envelope_center_m=((lo + hi) * 0.0005).tolist(),
            extent_m=(extent * 0.001).tolist(),
            min_m=(lo * 0.001).tolist(),
            max_m=(hi * 0.001).tolist(),
            volume_mm3=solid.Volume(),
            density_kg_m3=rho,
            collision="AABB envelope; internal pockets filled only for collision",
            binding={"interface": spec["interface"], "face": target},
        )
    need(len(set(used)) == 2, "Bodies must bind to different solids")
    base, car = bodies["base"], bodies["carriage"]
    need(
        all(
            base["min_m"][i] + 0.001 < car["min_m"][i] and car["max_m"][i] < base["max_m"][i] - 0.001
            for i in (0, 1)
        ),
        "Carriage swept path must lie inside base footprint",
    )
    gap = car["min_m"][2] - base["max_m"][2]
    need(0.005 <= gap <= 0.05, "Initial separation must be 5..50 mm")
    write("assembly-bindings.json", bodies)
    write("material-source.json", request["mechanism"]["material_sources"])
    return bodies


def nums(values):
    return " ".join(format(float(v), ".17g") for v in values)


def xml(bodies, s, dt):
    nodes = []
    for name, b in bodies.items():
        inertia = np.array(b["inertia_kg_m2"])
        packed = [inertia[0, 0], inertia[1, 1], inertia[2, 2], inertia[0, 1], inertia[0, 2], inertia[1, 2]]
        center = np.array(b["envelope_center_m"]) - b["com_m"]
        joint = (
            '<joint name="slide" type="slide" axis="0 0 1" damping="0" armature="0" frictionloss="0" limited="false"/>'
            if name == "carriage"
            else ""
        )
        nodes.append(
            f'<body name="{name}" pos="{nums(b["com_m"])}" quat="1 0 0 0">{joint}'
            f'<inertial pos="0 0 0" mass="{b["mass_kg"]}" fullinertia="{nums(packed)}"/>'
            f'<geom name="{name}" type="box" pos="{nums(center)}" size="{nums(np.array(b["extent_m"]) / 2)}" condim="1" friction="0 0 0" solref="{nums(s["solref"])}" solimp="{nums(s["solimp"])}"/></body>'
        )
    return f'''<mujoco model="validated_slider"><compiler angle="radian" inertiafromgeom="false"/>
<option timestep="{dt}" gravity="0 0 {-s["gravity_m_s2"]}" integrator="implicitfast" solver="Newton" iterations="100" tolerance="1e-12"><flag energy="enable"/></option>
<worldbody>{"".join(nodes)}</worldbody><actuator><motor name="lift" joint="slide" gear="1" ctrllimited="true" ctrlrange="0 {s["force_limit_n"]}" forcelimited="true" forcerange="0 {s["force_limit_n"]}"/></actuator></mujoco>'''


def compile_model(text, bodies):
    model = mujoco.MjModel.from_xml_string(text)
    need(model.nq == 1 and model.nv == 1 and model.nu == 1, "Unexpected mechanism DOFs")
    checks = {}
    for name, b in bodies.items():
        i = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        rotation = np.empty(9)
        mujoco.mju_quat2Mat(rotation, model.body_iquat[i])
        rotation = rotation.reshape(3, 3)
        reconstructed = rotation @ np.diag(model.body_inertia[i]) @ rotation.T
        need(
            np.allclose(reconstructed, b["inertia_kg_m2"], rtol=1e-8, atol=1e-14),
            "Compiled inertia differs from CAD integral",
        )
        need(math.isclose(model.body_mass[i], b["mass_kg"], rel_tol=1e-10), "Compiled mass differs from CAD")
        checks[name] = dict(
            mass_kg=float(model.body_mass[i]),
            inertia_kg_m2=reconstructed.tolist(),
            body_position_m=model.body_pos[i].tolist(),
        )
    return model, checks


def references(text, bodies):
    m, checks = compile_model(text, bodies)
    d = mujoco.MjData(m)
    # Motion oracle independent of integrator implementation: q=F*t²/(2m).
    m.opt.gravity[:] = 0
    force = min(0.05, float(m.actuator_ctrlrange[0, 1]))
    dt = m.opt.timestep
    n = 100
    for _ in range(n):
        d.ctrl[0] = force
        mujoco.mj_step(m, d)
    acceleration = force / bodies["carriage"]["mass_kg"]
    T = n * dt
    expected = 0.5 * acceleration * T * T
    error = abs(float(d.qpos[0]) - expected)
    bound = 0.51 * acceleration * T * dt + 1e-12
    if error > bound:
        raise Numerical("Constant force motion reference failed")
    # No actuation, gravity, damping or contact: rigid translation conserves KE and momentum.
    m, _ = compile_model(text, bodies)
    m.opt.gravity[:] = 0
    d = mujoco.MjData(m)
    d.qvel[0] = 0.1
    initial = 0.5 * bodies["carriage"]["mass_kg"] * 0.1**2
    for _ in range(100):
        mujoco.mj_step(m, d)
    final = 0.5 * bodies["carriage"]["mass_kg"] * float(d.qvel[0]) ** 2
    if abs(final - initial) > max(1e-12, initial * 1e-9):
        raise Numerical("Free-motion conservation reference failed")
    return dict(
        compiled_properties=checks,
        force_motion=dict(expected_m=expected, error_m=error, tolerance_m=bound),
        free_motion=dict(initial_energy_j=initial, final_energy_j=final, velocity_m_s=float(d.qvel[0])),
        conservation_scope="Only unforced gravity-free contact-free translation; dissipative contact is not energy conserving",
    )


def simulate(text, bodies, s, scenario, level):
    m, _ = compile_model(text, bodies)
    d = mujoco.MjData(m)
    dt = float(m.opt.timestep)
    n = round(s["duration_seconds"] / dt)
    rows = []
    peak = 0
    warning = False
    for step in range(n):
        target = s["target_m"] * min(float(d.time) / s["ramp_seconds"], 1)
        u = (
            0
            if scenario == "settle"
            else np.clip(
                bodies["carriage"]["mass_kg"] * s["gravity_m_s2"]
                + s["kp_n_m"] * (target - d.qpos[0])
                - s["kd_ns_m"] * d.qvel[0],
                0,
                s["force_limit_n"],
            )
        )
        d.ctrl[0] = u
        mujoco.mj_step(m, d)
        mujoco.mj_forward(m, d)
        normal = 0.0
        penetration = 0.0
        for k in range(d.ncon):
            contact = d.contact[k]
            wrench = np.zeros(6)
            mujoco.mj_contactForce(m, d, k, wrench)
            normal += float(wrench[0])
            penetration = max(penetration, -float(contact.dist))
        peak = max(peak, abs(float(d.actuator_force[0])))
        warning = warning or any(w.number for w in d.warning)
        if step % max(1, n // 2000) == 0 or step == n - 1:
            rows.append([float(d.time), float(d.qpos[0]), float(d.qvel[0]), float(u), normal, penetration])
    if warning or not np.isfinite(np.asarray(rows)).all():
        raise Numerical("MuJoCo warning or nonfinite trajectory")
    filename = f"{scenario}-{level}.csv"
    with (OUT / filename).open("w") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "q_m", "velocity_m_s", "actuator_n", "contact_normal_n", "penetration_m"])
        writer.writerows(rows)
    tail = np.array([r for r in rows if r[0] > s["duration_seconds"] - 0.2])
    if scenario == "settle":
        equilibrium = abs(float(np.mean(tail[:, 4])) - bodies["carriage"]["mass_kg"] * s["gravity_m_s2"])
        gap = bodies["carriage"]["min_m"][2] + float(d.qpos[0]) - bodies["base"]["max_m"][2]
        # Reference equilibrium must hold even for a deliberately underpowered design.
        if (
            equilibrium > max(0.001, bodies["carriage"]["mass_kg"] * s["gravity_m_s2"] * 0.01)
            or abs(d.qvel[0]) > 0.0001
            or gap > 0.0001
        ):
            raise Numerical("Settled contact equilibrium reference failed")
    else:
        equilibrium = 0
    return dict(
        final_q_m=float(d.qpos[0]),
        tracking_error_m=abs(float(d.qpos[0]) - s["target_m"]),
        settled_penetration_m=float(np.max(tail[:, 5])),
        equilibrium_error_n=equilibrium,
        peak_actuation_n=peak,
        steps=n,
        dt=dt,
        trajectory=filename,
    )


def run(request):
    start = time.monotonic()
    need(mujoco.__version__ == "3.4.0", "Untested MuJoCo runtime")
    bodies = inspect(request)
    s = request["mechanism"]["settings"]
    levels = []
    write("configuration.json", request["mechanism"])
    for level in range(3):
        dt = s["timestep_seconds"] / 2**level
        text = xml(bodies, s, dt)
        (OUT / f"mechanism-{level}.xml").write_text(text)
        if level == 0:
            write("reference-checks.json", references(text, bodies))
        levels.append({scenario: simulate(text, bodies, s, scenario, level) for scenario in s["scenarios"]})
    # Require convergence over both successive refinements, not just an accidentally close pair.
    differences = []

    def trajectory_difference(a, b):
        x = np.loadtxt(OUT / a["trajectory"], delimiter=",", skiprows=1)
        y = np.loadtxt(OUT / b["trajectory"], delimiter=",", skiprows=1)
        # Compare common physical times; exclude extrapolated pre-first-sample values.
        x = x[x[:, 0] >= y[0, 0]]
        return float(np.max(np.abs(x[:, 1] - np.interp(x[:, 0], y[:, 0], y[:, 1]))))

    for a, b in zip(levels, levels[1:]):
        differences.append(
            dict(
                position=max(trajectory_difference(a[k], b[k]) for k in s["scenarios"]),
                force=max(abs(a[k]["peak_actuation_n"] - b[k]["peak_actuation_n"]) for k in s["scenarios"]),
            )
        )
    converged = all(
        v["position"] <= s["max_position_difference_m"] and v["force"] <= s["max_force_difference_n"]
        for v in differences
    )
    write("convergence.json", dict(levels=levels, differences=differences, converged=converged, policy=s))
    write(
        "uncertainty.json",
        dict(
            scope="Declared nominal model allowance only; no measured contact/guide uncertainty",
            approximations=s["approximation"],
            contact="soft numerical normal compliance; friction zero",
        ),
    )
    write(
        "solver-resources.json",
        dict(
            steps=sum(v["steps"] for level in levels for v in level.values()),
            duration_seconds=time.monotonic() - start,
            peak_rss_kb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            cpu_backend="native CPU, no accelerator",
            refined_estimate="Actual compiled DOFs=1; measured steps, elapsed time and peak RSS; not adequacy proof",
        ),
    )
    if not converged:
        raise Numerical("Required timestep sensitivity not demonstrated")
    final = levels[-1]
    values = dict(
        mass_g=bodies["carriage"]["mass_kg"] * 1000,
        tracking_error_m=final["lift"]["tracking_error_m"],
        settled_penetration_m=final["settle"]["settled_penetration_m"],
        equilibrium_error_n=final["settle"]["equilibrium_error_n"],
        peak_actuation_n=final["lift"]["peak_actuation_n"],
    )
    errors = {
        "mass_g": 1e-7,
        "tracking_error_m": max(v["position"] for v in differences),
        "settled_penetration_m": max(v["position"] for v in differences),
        "equilibrium_error_n": max(
            abs(a["settle"]["equilibrium_error_n"] - b["settle"]["equilibrium_error_n"])
            for a, b in zip(levels, levels[1:])
        ),
        "peak_actuation_n": max(v["force"] for v in differences),
    }
    units = request["test"]["metrics"]
    return dict(
        test_id=request["test"]["id"],
        status="pass",
        reason="ok",
        applicable=True,
        mesh_valid=True,
        metrics={
            k: dict(
                value=v,
                unit=units[k],
                numerical_error=errors[k],
                uncertainty=0.0001 if units[k] == "m" else 0.001 if units[k] == "N" else 0.0,
            )
            for k, v in values.items()
        },
    )


def main():
    request = json.loads(Path("/input/request.json").read_text())
    try:
        result = run(request)
    except Invalid as e:
        result = dict(
            test_id=request["test"]["id"], status="invalid_setup", reason="invalid_binding", message=str(e)
        )
    except Numerical as e:
        result = dict(
            test_id=request["test"]["id"], status="numerical_failure", reason="solver_error", message=str(e)
        )
    except Exception as e:
        result = dict(
            test_id=request["test"]["id"],
            status="numerical_failure",
            reason="solver_error",
            message=type(e).__name__ + ": " + str(e),
        )
    write("result.json", result)
    print(
        json.dumps(
            {"solver": "MuJoCo 3.4.0 CPU", "status": result["status"], "message": result.get("message", "")}
        )
    )


if __name__ == "__main__":
    main()
