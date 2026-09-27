"""Bounded geometry utilities executed without network access or credentials."""

import os

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
import copy
import json
import time
from pathlib import Path

import numpy as np
from surface_geometry import build, profile, section_checks, seed, validate


def edit(spec, edits):
    result = copy.deepcopy(spec)
    for group in ("dimensions", "shape"):
        if group in edits:
            result[group].update(edits[group])
    for name in ("root", "tip"):
        if name in edits:
            result[name] = edits[name]
    for name in ("root", "tip"):
        if "thickness_scale" in edits or "camber_scale" in edits:
            t = edits.get("thickness_scale", 1)
            c = edits.get("camber_scale", 1)
            if not 0.85 <= t <= 1.4 or not 0.25 <= c <= 2:
                raise ValueError("Thickness scale [.85,1.4], camber scale [.25,2]")
            upper = np.array(result[name]["upper_weights"])
            lower = np.array(result[name]["lower_weights"])
            mean = (upper + lower) * 0.5 * c
            half = (upper - lower) * 0.5 * t
            result[name]["upper_weights"] = (mean + half).tolist()
            result[name]["lower_weights"] = (mean - half).tolist()
    unknown = set(edits) - {"dimensions", "shape", "root", "tip", "thickness_scale", "camber_scale"}
    if unknown:
        raise ValueError("Unknown edits: " + str(sorted(unknown)))
    section_checks(result)
    return result


def analyze(spec, conditions):
    if not 1 <= len(conditions) <= 30:
        raise ValueError("Provide 1–30 operating points")
    out = []
    for name in ("root", "tip"):
        foil = profile(spec[name])
        for c in conditions:
            re, alpha = float(c["reynolds"]), float(c["alpha_deg"])
            if not 100000 <= re <= 1500000 or not -8 <= alpha <= 14:
                raise ValueError("Re 100k–1.5M; alpha -8–14 degrees")
            r = foil.get_aero_from_neuralfoil(alpha=alpha, Re=re, model_size="xlarge")
            out.append(
                dict(
                    section=name,
                    **c,
                    **{k: float(np.asarray(r[k]).item()) for k in ("CL", "CD", "CM", "analysis_confidence")},
                )
            )
    return out


def optimize(spec, targets):
    from scipy.optimize import minimize

    started = time.monotonic()
    re = float(targets.get("reynolds", 300000))
    cl = float(targets.get("lift_coefficient", 0.6))
    thickness = float(targets.get("min_thickness", 0.12))
    if not 150000 <= re <= 800000 or not 0.3 <= cl <= 0.9 or not 0.11 <= thickness <= 0.16:
        raise ValueError("Optimizer targets: Re 150k–800k, CL .3–.9, minimum thickness .11–.16")
    original = spec["root"]
    initial = np.array(original["upper_weights"] + original["lower_weights"] + [3.0, 4.0, 5.0])
    x = np.linspace(0.01, 0.99, 80)
    count = 0

    def data(v):
        nonlocal count
        count += 1
        if time.monotonic() - started > 175:
            raise TimeoutError("Section optimization time limit")
        s = {**original, "upper_weights": v[:8].tolist(), "lower_weights": v[8:16].tolist()}
        f = profile(s)
        r = f.get_aero_from_neuralfoil(alpha=v[16:], Re=re * np.array([0.8, 1, 1.2]), model_size="xlarge")
        return f, r, s

    def objective(v):
        _, r, _ = data(v)
        return float(np.mean(r["CD"]) + 0.003 * np.sum((v[:16] - initial[:16]) ** 2))

    def constraints(v):
        f, r, _ = data(v)
        t = np.asarray(f.local_thickness(x))
        cam = np.asarray(f.local_camber(x))
        return np.r_[
            t - 0.001,
            0.18 - t,
            np.max(t) - thickness,
            float(f.local_thickness(0.25)) - max(0.11, thickness * 0.90),
            0.06 - np.abs(cam),
            np.asarray(r["analysis_confidence"]) - 0.95,
            0.12 - np.abs(r["CM"]),
            0.015 - np.abs(np.asarray(r["CL"]) - cl * np.array([0.85, 1, 1.15])),
        ]

    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(-0.5, 0.5)] * 16 + [(-2, 9)] * 3,
        constraints=[{"type": "ineq", "fun": constraints}],
        options={"maxiter": 200, "ftol": 1e-8},
    )
    f, r, s = data(result.x)
    if np.min(constraints(result.x)) < -0.001:
        raise ValueError("Optimizer did not find a supported feasible section")
    candidate = copy.deepcopy(spec)
    candidate["root"] = s
    candidate["tip"] = copy.deepcopy(s)
    section_checks(candidate)
    return dict(
        geometry=candidate,
        numerical_evaluations=count,
        seconds=time.monotonic() - started,
        converged=bool(result.success),
        conditions={"reynolds": re, "lift_coefficient": cl},
        mean_cd=float(np.mean(r["CD"])),
        min_confidence=float(np.min(r["analysis_confidence"])),
    )


def main():
    request = json.loads(Path("/input/request.json").read_text())
    action = request["action"]
    args = request["arguments"]
    if action == "seed":
        result = {"geometry": seed(args["parameters"])}
    elif action == "edit":
        result = {"geometry": edit(args["geometry"], args["edits"])}
    elif action == "analyze":
        result = {"sections": analyze(args["geometry"], args["conditions"])}
    elif action == "optimize":
        result = optimize(args["geometry"], args.get("targets", {}))
    elif action == "probe":
        from surface_physics import solve

        t = time.monotonic()
        values = [
            solve(args["geometry"], args["cg"], 15, alpha, -2, 6, nonlinear=True) for alpha in (4, 5, 6, 4)
        ]
        result = {"values": values, "seconds": time.monotonic() - t}
    elif action == "inspect":
        import inspect

        import aerosandbox as a

        result = {
            "init": str(inspect.signature(a.NonlinearLiftingLine)),
            "run": inspect.getsource(a.NonlinearLiftingLine.run)[:4000],
            "init_source": inspect.getsource(a.NonlinearLiftingLine.__init__)[:8000],
            "opti": str(inspect.signature(a.Opti.solve)),
        }
    elif action == "preview":
        spec = args["geometry"]
        validate(spec)
        assembly = build(spec)
        assembly.export("/output/model.step")
        assembly.export("/output/model.glb")
        import cadquery as cq

        actual = cq.importers.importStep("/output/model.step").solids().vals()
        if not actual or not all(s.isValid() for s in actual):
            raise ValueError("STEP round-trip validity failed")
        result = {"geometry": spec, "sections": section_checks(spec), "valid_solids": len(actual)}
    else:
        raise ValueError("Unsupported surface tool")
    Path("/output/result.json").write_text(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
