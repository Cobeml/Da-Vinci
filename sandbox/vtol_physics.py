"""Independent coupled screening. All lengths SI, power electrical, angles degrees."""

import json
import math
from pathlib import Path

import numpy as np
from scipy.interpolate import LinearNDInterpolator
from vtol_spec import SPECIFICATION as S

DATA = Path(__file__).parent / "vtol_data"


def tube(d, t):
    return math.pi / 4 * (d * d - (d - 2 * t) ** 2), math.pi / 64 * (d**4 - (d - 2 * t) ** 4)


def beam(force, length, d, t, distributed=False):
    _, i = tube(d, t)
    moment = force * length / (2 if distributed else 1)
    return {
        "stress_pa": moment * d / 2 / i,
        "deflection_m": force * length**3 / (8 if distributed else 3) / S["aluminium_e_pa"] / i,
    }


def tapered_wing_beam(force, length, diameter, wall, taper):
    x = np.linspace(0, length, 401)
    d = diameter * (1 - (1 - taper) * x / length)
    inertia = math.pi / 64 * (d**4 - (d - 2 * wall) ** 4)
    moment = force / (2 * length) * (length - x) ** 2
    return {
        "stress_pa": float(np.max(moment * d / (2 * inertia))),
        "deflection_m": float(np.trapezoid(moment * (length - x) / (S["aluminium_e_pa"] * inertia), x)),
    }


class Props:
    def __init__(self):
        self.static = np.loadtxt(DATA / "apce_16x8_static_2150od.txt", skiprows=1)
        points = []
        ct = []
        cp = []
        for path in sorted(DATA.glob("apce_12x8_*.txt")):
            if "static" in path.name:
                continue
            rpm = float(path.stem.split("_")[-1])
            rows = np.loadtxt(path, skiprows=1)
            for row in rows:
                points.append([rpm, row[0]])
                ct.append(row[1])
                cp.append(row[2])
        self.ct = LinearNDInterpolator(points, ct)
        self.cp = LinearNDInterpolator(points, cp)
        self.rpms = np.linspace(min(x[0] for x in points), max(x[0] for x in points), 150)

    def hover(self, force):
        rpms = np.linspace(self.static[0, 0], self.static[-1, 0], 600)
        n = rpms / 60
        d = S["lift_prop_diameter_m"]
        rho = S["rho"]
        thrust = np.interp(rpms, self.static[:, 0], self.static[:, 1]) * rho * n * n * d**4
        power = (
            np.interp(rpms, self.static[:, 0], self.static[:, 2])
            * rho
            * n**3
            * d**5
            / (S["motor_efficiency"] * S["esc_efficiency"])
        )
        valid = power <= S["lift_motor_limit_w"]
        capacity = float(max(thrust[valid]))
        if force > capacity or force < thrust[0]:
            return None, capacity
        return float(np.interp(force, thrust, power)), capacity

    def cruise(self, speed, drag):
        n = self.rpms / 60
        d = S["cruise_prop_diameter_m"]
        j = speed / n / d
        pts = np.column_stack([self.rpms, j])
        ct = self.ct(pts)
        cp = self.cp(pts)
        thrust = ct * S["rho"] * n * n * d**4
        power = cp * S["rho"] * n**3 * d**5 / (S["motor_efficiency"] * S["esc_efficiency"])
        valid = np.isfinite(power) & (thrust >= drag) & (power > 0) & (power <= S["cruise_motor_limit_w"])
        if not np.any(valid):
            return None
        idx = np.where(valid)[0][np.argmin(power[valid])]
        return dict(
            power_w=float(power[idx] + S["avionics_w"]),
            rpm=float(self.rpms[idx]),
            thrust_n=float(thrust[idx]),
        )


class Polars:
    def __init__(self):
        self.tables = json.loads((DATA / "polars.json").read_text())["polars"]

    def drag(self, code, re, cl):
        tabs = sorted([t for t in self.tables if t["airfoil"] == code], key=lambda t: t["reynolds"])
        if not tabs[0]["reynolds"] <= re <= tabs[-1]["reynolds"]:
            return None

        def at(t):
            r = np.array([x for x in t["rows"] if -5 <= x[0] <= 9])
            r = r[np.argsort(r[:, 1])]
            if not r[0, 1] <= cl <= r[-1, 1]:
                return None
            return float(np.interp(cl, r[:, 1], r[:, 2]))

        hi = next(i for i, t in enumerate(tabs) if t["reynolds"] >= re)
        lo = max(hi - 1, 0)
        a, b = at(tabs[lo]), at(tabs[hi])
        if a is None or b is None:
            return None
        if lo == hi:
            return a
        f = math.log(re / tabs[lo]["reynolds"]) / math.log(tabs[hi]["reynolds"] / tabs[lo]["reynolds"])
        return a + (b - a) * f


def aero_model(p, cg, resolution=10):
    import aerosandbox as a

    area = p["span"] * p["root_chord"] * (1 + p["taper"]) / 2
    mac = 2 / 3 * p["root_chord"] * (1 + p["taper"] + p["taper"] ** 2) / (1 + p["taper"])

    def airplane(elevator):
        wing = a.Wing(
            name="main",
            symmetric=True,
            xsecs=[
                a.WingXSec(
                    xyz_le=[p["wing_x"], 0, 0.08], chord=p["root_chord"], airfoil=a.Airfoil("naca2412")
                ),
                a.WingXSec(
                    xyz_le=[p["wing_x"] + p["sweep"], p["span"] / 2, 0.08],
                    chord=p["root_chord"] * p["taper"],
                    twist=p["twist_deg"],
                    airfoil=a.Airfoil("naca2412"),
                ),
            ],
        )
        tail = a.Wing(
            name="tail",
            symmetric=True,
            xsecs=[
                a.WingXSec(
                    xyz_le=[p["tail_x"] + offset, y, 0.22],
                    chord=c,
                    twist=p["tail_incidence_deg"] + elevator,
                    airfoil=a.Airfoil("naca0012"),
                    control_surfaces=[
                        a.ControlSurface(name="elevator", hinge_point=0.7, deflection=elevator)
                    ],
                )
                for offset, y, c in [
                    (0, 0, p["tail_chord"]),
                    (0.02, p["tail_span"] / 2, p["tail_chord"] * 0.7),
                ]
            ],
        )
        fin = a.Wing(
            name="fin",
            symmetric=False,
            xsecs=[
                a.WingXSec(
                    xyz_le=[p["fuselage_length"] * 0.78, 0, 0.03], chord=0.24, airfoil=a.Airfoil("naca0012")
                ),
                a.WingXSec(
                    xyz_le=[p["fuselage_length"] * 0.85, 0, 0.26], chord=0.17, airfoil=a.Airfoil("naca0012")
                ),
            ],
        )
        return a.Airplane(wings=[wing, tail, fin], xyz_ref=[cg, 0, 0], s_ref=area, c_ref=mac, b_ref=p["span"])

    samples = []
    for alpha, elevator in [(0, 0), (5, 0), (0, 5), (5, 5), (-5, 0), (0, -5)]:
        result = a.VortexLatticeMethod(
            airplane(elevator),
            a.OperatingPoint(velocity=20, alpha=alpha),
            spanwise_resolution=resolution,
            chordwise_resolution=max(4, resolution // 2),
        ).run()
        samples.append([alpha, elevator, *[float(result[k]) for k in ("CL", "Cm", "CD")]])
    r = np.array(samples)
    cl = np.array([r[0, 2], (r[1, 2] - r[4, 2]) / 10, (r[2, 2] - r[5, 2]) / 10])
    cm = np.array([r[0, 3], (r[1, 3] - r[4, 3]) / 10, (r[2, 3] - r[5, 3]) / 10])
    basis = np.array([[1, x, y, x * x, x * y, y * y] for x, y in r[:, :2]])
    drag = np.linalg.solve(basis, r[:, 4])
    # Directional stability check with the same fin geometry.
    beta = a.VortexLatticeMethod(
        airplane(0),
        a.OperatingPoint(velocity=20, alpha=0, beta=3),
        spanwise_resolution=resolution,
        chordwise_resolution=max(4, resolution // 2),
    ).run()
    return dict(
        area=area,
        mac=mac,
        cl=cl.tolist(),
        cm=cm.tolist(),
        drag=drag.tolist(),
        static_margin=float(-cm[1] / cl[1]),
        cnb_per_deg=float(beta["Cn"]) / 3,
        resolution=resolution,
        samples=r.tolist(),
    )


def structural(p, mass, payload):
    force = mass * S["gravity"] * S["maneuver_g"] * S["ultimate_factor"] / 2
    wing = tapered_wing_beam(force, p["span"] / 2, p["spar_diameter"], p["spar_wall"], p["taper"])
    arm = max(abs(p["wing_x"] + 0.25 * p["root_chord"] - p[k]) for k in ("rotor_front_x", "rotor_rear_x"))
    boom = beam(
        mass * S["gravity"] / 4 * S["hover_thrust_ratio"] * S["ultimate_factor"],
        arm,
        p["boom_diameter"],
        p["boom_wall"],
    )
    # Payload bay floor: simply supported rectangular strip, central landing load.
    width = 0.09
    thickness = p["shell_thickness"]
    length = 0.08
    f = payload * S["gravity"] * S["landing_g"] * S["ultimate_factor"]
    floor_stress = 1.5 * f * length / (width * thickness**2)
    return dict(
        wing=wing,
        boom=boom,
        payload_floor_stress_pa=floor_stress,
        passed=bool(
            wing["stress_pa"] <= S["aluminium_allowable_pa"]
            and boom["stress_pa"] <= S["aluminium_allowable_pa"]
            and wing["deflection_m"] <= p["span"] * S["tip_deflection_span_fraction"]
            and floor_stress <= 35e6
        ),
    )


def mass_properties(p, components, payload=0.5, empty_factor=1.0):
    # CG stays fixed under uniform empty-mass sensitivity scaling.
    items = [(x["mass_kg"] * empty_factor, x["cg_x_m"]) for x in components if x["name"] != "payload"] + [
        (payload, p["payload_x"])
    ]
    total = sum(x[0] for x in items)
    return total, sum(m * x for m, x in items) / total


def mission(
    p, components, aero, props, polars, payload=0.5, energy_factor=1.0, drag_factor=1.0, empty_factor=1.0
):
    mass, cg = mass_properties(p, components, payload, empty_factor)
    # Move the moment reference analytically for payload and empty-mass changes.
    ref_mass, ref_cg = mass_properties(p, components)
    cl = np.array(aero["cl"])
    cm = np.array(aero["cm"]) + (cg - ref_cg) / aero["mac"] * cl
    static_margin = -cm[1] / cl[1]
    aft = (cg - p["rotor_front_x"]) / (p["rotor_rear_x"] - p["rotor_front_x"])
    rotor_forces = [mass * S["gravity"] * (1 - aft) / 2, mass * S["gravity"] * aft / 2]
    h = [props.hover(f) for f in rotor_forces]
    structure = structural(p, mass, payload)
    failures = []
    if mass > S["max_mass_kg"]:
        failures.append("MASS_LIMIT")
    if not S["static_margin_range"][0] <= static_margin <= S["static_margin_range"][1]:
        failures.append("STATIC_MARGIN")
    if aero["cnb_per_deg"] <= 0:
        failures.append("DIRECTIONAL_STABILITY")
    if not structure["passed"]:
        failures.append("STRUCTURE")
    if any(v[0] is None for v in h) or not 0 < aft < 1:
        failures.append("HOVER_POWER")
    hover = sum((v[0] or 1e6) * 2 for v in h) + S["avionics_w"]
    thrust_ratio = min(v[1] / f for v, f in zip(h, rotor_forces)) if min(rotor_forces) > 0 else 0
    if thrust_ratio < S["hover_thrust_ratio"]:
        failures.append("HOVER_RESERVE")
    if hover > S["battery_power_limit_w"]:
        failures.append("BATTERY_POWER")
    overhead = hover * (S["hover_seconds"] + S["transition_seconds"] * S["transition_power_factor"]) / 3600
    usable = S["battery_wh"] * energy_factor * (1 - S["reserve_fraction"])
    available = usable - overhead
    if available <= 0:
        failures.append("MISSION_ENERGY")
    area = aero["area"]
    mac = aero["mac"]
    rho = S["rho"]
    weight = mass * S["gravity"]
    stall = math.sqrt(2 * weight / (rho * area * S["stall_cl_limit"]))
    curve = []
    for speed in np.arange(8.0, 30.01, 0.25):
        if speed < stall * S["stall_speed_factor"]:
            continue
        q = 0.5 * rho * speed**2
        target = weight / (q * area)
        alpha, elev = np.linalg.solve(np.array([cl[1:], cm[1:]]), [target - cl[0], -cm[0]])
        if not -5 <= alpha <= 10 or abs(elev) > S["max_elevator_deg"]:
            continue
        re = rho * speed * mac / S["viscosity"]
        cdwing = polars.drag("2412", re, target)
        # Tail lift estimated from downwash-corrected incidence and elevator effectiveness.
        tail_cl = 0.075 * (alpha * 0.6 + p["tail_incidence_deg"] + elev)
        cdtail = polars.drag("0012", rho * speed * p["tail_chord"] * 0.85 / S["viscosity"], tail_cl)
        if cdwing is None or cdtail is None:
            continue
        cdi = float(np.dot(aero["drag"], [1, alpha, elev, alpha**2, alpha * elev, elev**2]))
        if cdi < 0:
            continue
        # Turbulent skin-friction/form-factor buildup; all areas explicitly dimensional.
        length = p["fuselage_length"]
        diam = math.sqrt(p["fuselage_width"] * p["fuselage_height"])
        fineness = length / diam
        cf = 0.455 / math.log10(rho * speed * length / S["viscosity"]) ** 2.58
        fuselage_area = math.pi * diam * length * 0.82
        body_drag = q * cf * (1 + 60 / fineness**3 + fineness / 400) * fuselage_area
        boom_drag = q * 0.008 * 2 * math.pi * p["boom_diameter"] * (p["rotor_rear_x"] - p["rotor_front_x"])
        # Fixed pods, skids and stopped lift blades; no favorable folding assumption.
        hardware_drag = q * (0.0022 + 4 * 0.4064 * 0.024 * 0.10)
        profile = q * (cdwing * area + cdtail * p["tail_span"] * p["tail_chord"] * 0.85 + 0.009 * 0.05)
        parasite = (body_drag + boom_drag + hardware_drag + profile) * drag_factor
        drag = q * area * cdi + parasite
        prop = props.cruise(speed, drag)
        if prop is None:
            continue
        power = prop["power_w"]
        if power > S["battery_power_limit_w"]:
            continue
        whkm = power / (speed * 3.6)
        curve.append(
            dict(
                speed_m_s=float(speed),
                range_km=max(0, available / whkm),
                cruise_minutes=max(0, available / power * 60),
                power_w=power,
                wh_km=whkm,
                drag_n=drag,
                induced_drag_n=q * area * cdi,
                body_drag_n=body_drag * drag_factor,
                profile_drag_n=profile * drag_factor,
                hardware_drag_n=(hardware_drag + boom_drag) * drag_factor,
                lift_drag=weight / drag,
                alpha_deg=float(alpha),
                elevator_deg=float(elev),
                rpm=prop["rpm"],
            )
        )
    if not curve:
        failures.append("NO_SUPPORTED_CRUISE")
    best = max(curve, key=lambda x: x["range_km"]) if curve else None
    return dict(
        mass_kg=mass,
        cg_x_m=cg,
        static_margin=float(static_margin),
        stall_speed_m_s=stall,
        hover_power_w=hover,
        hover_thrust_ratio=thrust_ratio,
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


def evaluate_performance(p, components, resolution=10):
    mass, cg = mass_properties(p, components)
    aero = aero_model(p, cg, resolution)
    props = Props()
    polars = Polars()
    nominal = mission(p, components, aero, props, polars)
    scenarios = {
        name: mission(p, components, aero, props, polars, **kw)
        for name, kw in {
            "battery_minus_10": {"energy_factor": 0.9},
            "parasite_plus_20": {"drag_factor": 1.2},
            "empty_mass_plus_10": {"empty_factor": 1.1},
            "combined_adverse": {"energy_factor": 0.9, "drag_factor": 1.2, "empty_factor": 1.1},
        }.items()
    }
    payload_curve = []
    # Capacity includes the fixed bay volume; varying payload implies varying density, not size.
    cap = 0.12 * 0.10 * 0.08 * S["payload_density_kg_m3"]
    lo, hi = 0.0, cap
    for payload in np.linspace(0, cap, 11):
        m = mission(p, components, aero, props, polars, payload=float(payload))
        payload_curve.append(
            dict(
                payload_kg=float(payload),
                range_km=m["range_km"],
                feasible=not m["violations"],
                violations=m["violations"],
            )
        )
    # Feasibility can be non-monotonic because CG changes; refine above the largest passing sample.
    passing = [
        x["payload_kg"] for x in payload_curve if x["feasible"] and x["range_km"] >= S["payload_mission_km"]
    ]
    capacity = max(passing, default=0)
    if passing and capacity < cap:
        lo = capacity
        hi = min(cap, capacity + cap / 10)
        for _ in range(8):
            mid = (lo + hi) / 2
            m = mission(p, components, aero, props, polars, payload=mid)
            if not m["violations"] and m["range_km"] >= S["payload_mission_km"]:
                lo = mid
            else:
                hi = mid
        capacity = lo
    return dict(
        nominal=nominal,
        aero=aero,
        payload_capacity_kg=capacity,
        payload_curve=payload_curve,
        scenarios={
            k: {kk: v[kk] for kk in ("range_km", "violations", "max_speed_m_s", "mass_kg")}
            for k, v in scenarios.items()
        },
    )
