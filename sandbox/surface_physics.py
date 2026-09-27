"""CST-sensitive aerodynamic screening. Frozen separately from the original study."""

import math

import aerosandbox as a
import numpy as np
from surface_geometry import profile, stations
from vtol_physics import Props, mass_properties, structural
from vtol_spec import SPECIFICATION as S

_NONLINEAR = {}


class ParametricNonlinear:
    """Build the implicit flow equations once; reuse them for each operating point."""

    def __init__(self, spec, cg, resolution):
        self.opti = a.Opti()
        self.params = [self.opti.parameter(value=v) for v in (15.0, 4.0, 0.0, 0.0)]
        speed, alpha, elevator, beta = self.params
        self.analysis = a.NonlinearLiftingLine(
            airplane(spec, cg, elevator),
            a.OperatingPoint(velocity=speed, alpha=alpha, beta=beta),
            spanwise_resolution=resolution,
            verbose=False,
            opti=self.opti,
        )
        self.raw = self.analysis.run(solve=False)
        self.opti.subject_to(self.raw["residuals"] == 0)
        self.opti.solver(
            "ipopt",
            {"print_time": False, "ipopt.print_level": 0, "ipopt.max_iter": 100, "ipopt.max_cpu_time": 60},
        )
        self.solution = None

    def run(self, speed, alpha, elevator, beta):
        import casadi

        for parameter, value in zip(self.params, (speed, alpha, elevator, beta)):
            self.opti.set_value(parameter, value)
        if self.solution is not None:
            self.opti.set_initial(self.opti.x, self.solution.value(self.opti.x))
        self.solution = casadi.Opti.solve(self.opti)
        return {k: float(self.solution.value(self.raw[k])) for k in ("CL", "CD", "Cm", "Cn")}


def airplane(spec, cg, elevator=0):
    p = spec["dimensions"]
    sections = stations(spec)
    wing = a.Wing(
        name="main",
        symmetric=True,
        xsecs=[
            a.WingXSec(
                xyz_le=[s["x"], s["y"], s["z"]],
                chord=s["chord"],
                twist=s["twist"],
                airfoil=profile(s["section"]),
            )
            for s in sections
        ],
    )
    tail = a.Wing(
        name="tail",
        symmetric=True,
        xsecs=[
            a.WingXSec(
                xyz_le=[p["tail_x"] + x, y, 0.22],
                chord=c,
                twist=p["tail_incidence_deg"] + elevator,
                airfoil=a.Airfoil("naca0012"),
            )
            for x, y, c in [(0, 0, p["tail_chord"]), (0.02, p["tail_span"] / 2, p["tail_chord"] * 0.7)]
        ],
    )
    fin = a.Wing(
        name="fin",
        symmetric=False,
        xsecs=[
            a.WingXSec(xyz_le=[p["fuselage_length"] * x, 0, z], chord=c, airfoil=a.Airfoil("naca0012"))
            for x, z, c in [(0.78, 0.03, 0.24), (0.85, 0.26, 0.17)]
        ],
    )
    return a.Airplane(
        wings=[wing, tail, fin],
        xyz_ref=[cg, 0, 0],
        s_ref=wing.area(),
        c_ref=wing.mean_aerodynamic_chord(),
        b_ref=p["span"],
    )


def solve(spec, cg, speed, alpha, elevator, resolution, nonlinear=False, details=False, beta=0):
    if nonlinear and not details:
        import json

        key = (json.dumps(spec, sort_keys=True), cg, resolution)
        if key not in _NONLINEAR:
            _NONLINEAR[key] = ParametricNonlinear(spec, cg, resolution)
        return _NONLINEAR[key].run(speed, alpha, elevator, beta)
    cls = a.NonlinearLiftingLine if nonlinear else a.LiftingLine
    analysis = cls(
        airplane(spec, cg, elevator),
        a.OperatingPoint(velocity=speed, alpha=alpha, beta=beta),
        spanwise_resolution=resolution,
        verbose=False,
    )
    raw = analysis.run()
    out = {k: float(raw[k]) for k in ("CL", "CD", "Cm", "Cn")}
    if not all(math.isfinite(v) for v in out.values()) or out["CD"] <= 0:
        raise ValueError("Aerodynamic solver returned unsupported coefficients")
    if details:
        velocity = np.asarray(
            analysis.get_velocity_at_points(
                analysis.vortex_centers, vortex_strengths=analysis.vortex_strengths
            )
        )
        magnitude = np.linalg.norm(velocity, axis=1)
        alpha_local = np.degrees(
            np.arcsin(np.clip(np.sum(velocity * analysis.normal_directions, axis=1) / magnitude, -1, 1))
        )
        reynolds = (
            magnitude * np.asarray(analysis.chords) / analysis.op_point.atmosphere.kinematic_viscosity()
        )
        confidence, section_drag, section_lift = [], [], []
        for i, foil in enumerate(analysis.airfoils):
            r = foil.get_aero_from_neuralfoil(
                alpha=float(alpha_local[i]), Re=float(reynolds[i]), model_size="xlarge"
            )
            confidence.append(float(np.asarray(r["analysis_confidence"]).item()))
            section_drag.append(float(np.asarray(r["CD"]).item()))
            section_lift.append(float(np.asarray(r["CL"]).item()))
        q = 0.5 * float(analysis.op_point.atmosphere.density()) * magnitude**2
        out.update(
            min_confidence=min(confidence),
            local_alpha=alpha_local.tolist(),
            local_reynolds=reynolds.tolist(),
            local_cl=section_lift,
            panel_y=np.asarray(analysis.vortex_centers)[:, 1].tolist(),
            panel_lift=(q * np.array(section_lift) * np.asarray(analysis.areas)).tolist(),
            profile_drag_n=float(np.sum(q * np.array(section_drag) * np.asarray(analysis.areas))),
        )
        forces = (
            float(analysis.op_point.atmosphere.density())
            * np.cross(velocity, analysis.vortex_bound_leg)
            * np.asarray(analysis.vortex_strengths).reshape(-1, 1)
        )
        out["panel_lift"] = forces[:, 2].tolist()
        out["main_panel_count"] = 4 * resolution
    return out


def aero_model(spec, cg, resolution, nonlinear):
    plane = airplane(spec, cg)
    tables = []
    alpha_grid = [-4.0, -2.0, 0.0, 2.0, 4.0, 6.0, 8.0]
    elevator_grid = [-10.0, -7.5, -5.0, -2.5, 0.0, 2.5, 5.0, 7.5, 10.0]
    for speed in (10.0, 15.0, 20.0, 25.0, 30.0):
        values = [
            [solve(spec, cg, speed, alpha, elev, resolution, nonlinear) for elev in elevator_grid]
            for alpha in alpha_grid
        ]
        tables.append(
            dict(
                speed=speed, **{key: [[v[key] for v in row] for row in values] for key in ("CL", "Cm", "CD")}
            )
        )
    # A conservative attached-flow section limit replaces the fixed aircraft CLmax.
    limits = []
    for s in stations(spec):
        alphas = np.arange(-2.0, 15.1, 0.5)
        polar = profile(s["section"]).get_aero_from_neuralfoil(
            alpha=alphas, Re=1.225 * 12 * s["chord"] / S["viscosity"], model_size="xlarge"
        )
        cls = np.asarray(polar["CL"])
        conf = np.asarray(polar["analysis_confidence"])
        valid = (conf >= 0.95) & (np.gradient(cls, alphas) > 0.02)
        limits.append(float(max(cls[valid], default=0)) * 0.85)
    return dict(
        area=float(plane.s_ref),
        mac=float(plane.c_ref),
        tables=tables,
        alpha_grid=alpha_grid,
        elevator_grid=elevator_grid,
        cl_limit=min(limits),
        cnb_per_deg=solve(spec, cg, 20, 0, 0, resolution, nonlinear, beta=3)["Cn"] / 3,
        resolution=resolution,
        solver="nonlinear_lifting_line" if nonlinear else "lifting_line",
        surrogate="Reynolds-dependent cubic trim/drag interpolation with direct best-point audit",
    )


class AeroTable:
    def __init__(self, aero):
        from scipy.interpolate import RectBivariateSpline

        self.speeds = np.array([t["speed"] for t in aero["tables"]])
        self.splines = [
            {
                key: RectBivariateSpline(aero["alpha_grid"], aero["elevator_grid"], t[key])
                for key in ("CL", "Cm", "CD")
            }
            for t in aero["tables"]
        ]

    def evaluate(self, speed, alpha, elevator, derivative=False):
        hi = max(1, min(len(self.speeds) - 1, int(np.searchsorted(self.speeds, speed))))
        lo = hi - 1
        f = (speed - self.speeds[lo]) / (self.speeds[hi] - self.speeds[lo])
        return {
            key: float(
                (1 - f) * self.splines[lo][key].ev(alpha, elevator, dx=int(derivative))
                + f * self.splines[hi][key].ev(alpha, elevator, dx=int(derivative))
            )
            for key in ("CL", "Cm", "CD")
        }

    def trim(self, speed, target, reference_shift):
        from scipy.optimize import root

        def residual(x):
            v = self.evaluate(speed, *x)
            return [v["CL"] - target, v["Cm"] + reference_shift * v["CL"]]

        r = root(residual, [3.0, 0.0], tol=1e-8)
        if not r.success or np.max(np.abs(residual(r.x))) > 1e-5:
            return None
        alpha, elev = r.x
        if not -4 <= alpha <= 8 or abs(elev) > 10:
            return None
        v = self.evaluate(speed, alpha, elev)
        d = self.evaluate(speed, alpha, elev, True)
        if d["CL"] <= 0:
            return None
        return float(alpha), float(elev), v["CD"], -d["Cm"] / d["CL"] - reference_shift


def mission(
    spec,
    components,
    aero,
    props,
    wetted,
    table,
    payload=0.5,
    energy_factor=1.0,
    drag_factor=1.0,
    empty_factor=1.0,
):
    p = spec["dimensions"]
    mass, cg = mass_properties(p, components, payload, empty_factor)
    _, refcg = mass_properties(p, components)
    aft = (cg - p["rotor_front_x"]) / (p["rotor_rear_x"] - p["rotor_front_x"])
    forces = [mass * S["gravity"] * (1 - aft) / 2, mass * S["gravity"] * aft / 2]
    h = [props.hover(f) for f in forces]
    hover = sum((v[0] or 1e6) * 2 for v in h) + S["avionics_w"]
    thrust = min(v[1] / f for v, f in zip(h, forces)) if min(forces) > 0 else 0
    structure = structural(p, mass, payload)
    failures = []
    for condition, code in [
        (mass > S["max_mass_kg"], "MASS_LIMIT"),
        (not structure["passed"], "STRUCTURE"),
        (any(x[0] is None for x in h) or not 0 < aft < 1, "HOVER_POWER"),
        (thrust < S["hover_thrust_ratio"], "HOVER_RESERVE"),
        (hover > S["battery_power_limit_w"], "BATTERY_POWER"),
        (aero["cnb_per_deg"] <= 0, "DIRECTIONAL_STABILITY"),
    ]:
        if condition:
            failures.append(code)
    overhead = hover * (S["hover_seconds"] + S["transition_seconds"] * S["transition_power_factor"]) / 3600
    usable = S["battery_wh"] * energy_factor * (1 - S["reserve_fraction"])
    available = usable - overhead
    if available <= 0:
        failures.append("MISSION_ENERGY")
    weight = mass * S["gravity"]
    area = aero["area"]
    mac = aero["mac"]
    stall = math.sqrt(2 * weight / (S["rho"] * area * max(0.05, aero["cl_limit"])))
    curve = []
    for speed in np.arange(10.0, 30.01, 0.25):
        if speed < stall * S["stall_speed_factor"]:
            continue
        q = 0.5 * S["rho"] * speed**2
        target = weight / (q * area)
        trim = table.trim(speed, target, (cg - refcg) / mac)
        if trim is None:
            continue
        alpha, elev, cd, margin = trim
        if not S["static_margin_range"][0] <= margin <= S["static_margin_range"][1] or cd <= 0:
            continue
        length = p["fuselage_length"]
        diameter = math.sqrt(p["fuselage_width"] * p["fuselage_height"])
        f = length / diameter
        cf = 0.455 / math.log10(S["rho"] * speed * length / S["viscosity"]) ** 2.58
        body = q * cf * (1 + 60 / f**3 + f / 400) * wetted["body"]
        covers = q * 0.008 * wetted["fairings"]
        hardware = q * (0.0022 + 4 * 0.4064 * 0.024 * 0.10)
        # The lifting-line CD already includes profile and induced drag exactly once.
        drag = (q * area * cd + body + covers + hardware) * drag_factor
        prop = props.cruise(speed, drag)
        if prop is None:
            continue
        power = prop["power_w"]
        whkm = power / (speed * 3.6)
        if power > S["battery_power_limit_w"]:
            continue
        curve.append(
            dict(
                speed_m_s=float(speed),
                range_km=max(0, available / whkm),
                cruise_minutes=max(0, available / power * 60),
                power_w=power,
                wh_km=whkm,
                drag_n=drag,
                lifting_surfaces_drag_n=q * area * cd * drag_factor,
                body_drag_n=body * drag_factor,
                hardware_drag_n=(hardware + covers) * drag_factor,
                lift_drag=weight / drag,
                alpha_deg=float(alpha),
                elevator_deg=float(elev),
                rpm=prop["rpm"],
                static_margin=margin,
            )
        )
    if not curve:
        failures.append("NO_SUPPORTED_CRUISE")
    best = max(curve, key=lambda x: x["range_km"]) if curve else None
    return dict(
        mass_kg=mass,
        cg_x_m=cg,
        static_margin=best["static_margin"] if best else 0,
        stall_speed_m_s=stall,
        hover_power_w=hover,
        hover_thrust_ratio=thrust,
        overhead_wh=overhead,
        usable_wh=usable,
        reserve_wh=S["battery_wh"] * energy_factor * S["reserve_fraction"],
        structure=structure,
        range_km=best["range_km"] if best else 0,
        best=best,
        max_speed_m_s=max((x["speed_m_s"] for x in curve), default=0),
        endurance_min=max((x["cruise_minutes"] for x in curve), default=0)
        + (S["hover_seconds"] + S["transition_seconds"]) / 60,
        curve=curve,
        violations=failures,
    )


def evaluate_performance(spec, components, resolution=6, nonlinear=False, wetted=None):
    p = spec["dimensions"]
    _, cg = mass_properties(p, components)
    aero = aero_model(spec, cg, resolution, nonlinear)
    props = Props()
    table = AeroTable(aero)

    def run(**kwargs):
        return mission(spec, components, aero, props, wetted, table, **kwargs)

    nominal = run()
    scenarios = {
        name: run(**kw)
        for name, kw in {
            "battery_minus_10": {"energy_factor": 0.9},
            "parasite_plus_20": {"drag_factor": 1.2},
            "empty_mass_plus_10": {"empty_factor": 1.1},
            "combined_adverse": {"energy_factor": 0.9, "drag_factor": 1.2, "empty_factor": 1.1},
        }.items()
    }
    payloads = []
    for payload in np.linspace(0, 0.96, 21):
        n = run(payload=float(payload))
        payloads.append(
            dict(
                payload_kg=float(payload),
                range_km=n["range_km"],
                feasible=not n["violations"],
                violations=n["violations"],
            )
        )
    best = nominal["best"]
    audit = None
    if best:
        audit = solve(
            spec,
            cg,
            best["speed_m_s"],
            best["alpha_deg"],
            best["elevator_deg"],
            resolution,
            nonlinear,
            details=True,
        )
        q = 0.5 * S["rho"] * best["speed_m_s"] ** 2
        errors = dict(
            lift_relative=abs(audit["CL"] * q * aero["area"] / (nominal["mass_kg"] * S["gravity"]) - 1),
            moment_absolute=abs(audit["Cm"]),
            drag_relative=abs(audit["CD"] * q * aero["area"] / best["lifting_surfaces_drag_n"] - 1),
        )
        audit["surrogate_errors"] = errors
        if (
            errors["lift_relative"] > 0.03
            or errors["moment_absolute"] > 0.01
            or errors["drag_relative"] > 0.05
        ):
            nominal["violations"].append("AERO_SURROGATE_ERROR")
        if audit["min_confidence"] < 0.95:
            nominal["violations"].append("SECTION_SUPPORT")
        # Integrate actual main-wing panel loads and retain the conservative uniform-load result.
        count = audit["main_panel_count"]
        ys = np.abs(np.array(audit["panel_y"][:count]))
        loads = np.maximum(np.array(audit["panel_lift"][:count]), 0)
        xs = np.linspace(0, p["span"] / 2, 401)
        moments = (
            np.sum(np.maximum(ys[None, :] - xs[:, None], 0) * loads[None, :], axis=1)
            / 2
            * S["maneuver_g"]
            * S["ultimate_factor"]
        )
        diameter = p["spar_diameter"] * (1 - (1 - p["taper"]) * xs / (p["span"] / 2))
        inertia = math.pi / 64 * (diameter**4 - (diameter - 2 * p["spar_wall"]) ** 4)
        stress = float(np.max(moments * diameter / 2 / inertia))
        deflection = float(np.trapezoid(moments * (p["span"] / 2 - xs) / (S["aluminium_e_pa"] * inertia), xs))
        wing = nominal["structure"]["wing"]
        wing["stress_pa"] = max(wing["stress_pa"], stress)
        wing["deflection_m"] = max(wing["deflection_m"], deflection)
        nominal["structure"]["spanwise_load_screen"] = {"stress_pa": stress, "deflection_m": deflection}
        if (
            wing["stress_pa"] > S["aluminium_allowable_pa"]
            or wing["deflection_m"] > p["span"] * S["tip_deflection_span_fraction"]
        ):
            nominal["violations"].append("SPANWISE_STRUCTURE")
    return dict(
        nominal=nominal,
        aero=aero,
        direct_audit=audit,
        payload_capacity_kg=max(
            (x["payload_kg"] for x in payloads if x["feasible"] and x["range_km"] >= 10), default=0
        ),
        payload_curve=payloads,
        scenarios={
            k: {key: v[key] for key in ("range_km", "violations", "max_speed_m_s", "mass_kg")}
            for k, v in scenarios.items()
        },
    )
