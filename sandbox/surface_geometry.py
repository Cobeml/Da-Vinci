"""Versioned CST/spline aircraft geometry; metres in specifications, mm in CAD."""

import copy
import math

import numpy as np

try:
    from vtol_family import BOUNDS
    from vtol_family import parts as legacy_parts
except ImportError:
    from sandbox.vtol_family import BOUNDS
    from sandbox.vtol_family import parts as legacy_parts

VERSION = 1
SHAPE_BOUNDS = {
    "mid_chord_factor": (0.9, 1.1),
    "mid_twist_offset": (-0.75, 0.75),
    "nose_fullness": (0.85, 1.15),
    "shoulder_fullness": (0.95, 1.1),
    "tail_fullness": (0.85, 1.15),
}


def profile(spec):
    import aerosandbox as a

    return a.KulfanAirfoil(
        name="cst", **{k: np.array(v) if isinstance(v, list) else v for k, v in spec.items()}
    )


def seed(parameters):
    import aerosandbox as a

    airfoil = a.Airfoil("naca2412").to_kulfan_airfoil(n_weights_per_side=8)
    section = {
        k: np.asarray(getattr(airfoil, k)).tolist()
        for k in ("upper_weights", "lower_weights", "leading_edge_weight", "TE_thickness")
    }
    return {
        "version": VERSION,
        "dimensions": parameters,
        "root": section,
        "tip": copy.deepcopy(section),
        "shape": {k: (0 if k == "mid_twist_offset" else 1) for k in SHAPE_BOUNDS},
    }


def validate(spec):
    if set(spec) != {"version", "dimensions", "root", "tip", "shape"} or spec["version"] != VERSION:
        raise ValueError("GeometrySpec requires version=1, dimensions, root, tip, shape")
    p = spec["dimensions"]
    if set(p) != set(BOUNDS):
        raise ValueError("Use exactly the documented dimension fields")
    for key, (low, high) in BOUNDS.items():
        v = p[key]
        if (
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not math.isfinite(v)
            or not low <= v <= high
        ):
            raise ValueError(f"dimensions.{key} must be finite in [{low}, {high}]")
    if p["tail_x"] + p["tail_chord"] > p["fuselage_length"] + 0.14:
        raise ValueError("Tail trailing edge must remain near the fuselage tail")
    # Actual CST/STEP containment replaces the fixed-NACA spar/chord restriction.
    if set(spec["shape"]) != set(SHAPE_BOUNDS):
        raise ValueError("Use exactly the documented shape fields")
    for key, (low, high) in SHAPE_BOUNDS.items():
        v = spec["shape"][key]
        if (
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not math.isfinite(v)
            or not low <= v <= high
        ):
            raise ValueError(f"shape.{key} must be finite in [{low}, {high}]")
    for name in ("root", "tip"):
        s = spec[name]
        if set(s) != {"upper_weights", "lower_weights", "leading_edge_weight", "TE_thickness"}:
            raise ValueError(f"{name}: invalid CST fields")
        for key in ("upper_weights", "lower_weights"):
            if not isinstance(s[key], list) or len(s[key]) != 8:
                raise ValueError(f"{name}.{key}: exactly eight coefficients required")
            if any(
                isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) or abs(x) > 0.6
                for x in s[key]
            ):
                raise ValueError(f"{name}.{key}: coefficients must be finite in [-0.6, 0.6]")
        for key, low, high in (("leading_edge_weight", -0.3, 0.3), ("TE_thickness", 0, 0.005)):
            v = s[key]
            if (
                isinstance(v, bool)
                or not isinstance(v, (float, int))
                or not math.isfinite(v)
                or not low <= v <= high
            ):
                raise ValueError(f"{name}.{key}: must be finite in [{low}, {high}]")


def stations(spec):
    p, s = spec["dimensions"], spec["shape"]
    out = []
    for f in (0, 0.5, 1):
        section = {
            k: ((1 - f) * np.array(spec["root"][k]) + f * np.array(spec["tip"][k])).tolist()
            for k in spec["root"]
        }
        chord = p["root_chord"] * (1 - f + f * p["taper"]) * (s["mid_chord_factor"] if f == 0.5 else 1)
        twist = f * p["twist_deg"] + (s["mid_twist_offset"] if f == 0.5 else 0)
        # Preserve the original straight quarter-chord line when changing middle chord.
        x = p["wing_x"] + f * p["sweep"] + 0.25 * (p["root_chord"] * (1 - f + f * p["taper"]) - chord)
        out.append(
            dict(fraction=f, x=x, y=f * p["span"] / 2, z=0.08, chord=chord, twist=twist, section=section)
        )
    return out


def section_checks(spec):
    validate(spec)
    result = []
    for station in stations(spec):
        foil = profile(station["section"])
        x = np.linspace(0.002, 0.998, 300)
        thickness = np.asarray(foil.local_thickness(x))
        camber = np.asarray(foil.local_camber(x))
        if thickness.min() <= 0 or not 0.105 <= thickness.max() <= 0.18:
            raise ValueError("Airfoil must not cross; maximum thickness must be 10.5–18% chord")
        if np.max(np.abs(camber)) > 0.06:
            raise ValueError("Maximum airfoil camber is 6% chord")
        result.append(
            {
                "fraction": station["fraction"],
                "thickness_ratio": float(thickness.max()),
                "camber_ratio": float(camber.max()),
            }
        )
    return result


def wing_wire(station, sign):
    import cadquery as cq

    foil = profile(station["section"])
    x = (1 - np.cos(np.linspace(0, math.pi, 61))) / 2
    upper = np.asarray(foil.upper_coordinates(x))
    lower = np.asarray(foil.lower_coordinates(x))
    angle = math.radians(station["twist"])

    def point(pt):
        xx, zz = pt * station["chord"]
        return cq.Vector(
            1000 * (station["x"] + xx * math.cos(angle) + zz * math.sin(angle)),
            1000 * sign * station["y"],
            1000 * (station["z"] - xx * math.sin(angle) + zz * math.cos(angle)),
        )

    edges = [
        cq.Edge.makeSpline([point(v) for v in upper]),
        cq.Edge.makeSpline([point(v) for v in lower[::-1]]),
    ]
    if (point(upper[-1]) - point(lower[-1])).Length > 1e-7:
        edges.insert(1, cq.Edge.makeLine(point(upper[-1]), point(lower[-1])))
    return cq.Wire.assembleEdges(edges)


def body_stations(spec):
    p, s = spec["dimensions"], spec["shape"]
    return [
        (0, 0.04),
        (0.12, 0.60 * s["nose_fullness"]),
        (p["nose_fraction"], 1),
        (0.52, s["shoulder_fullness"]),
        (p["tail_fraction"], 0.84),
        (0.9, 0.43 * s["tail_fullness"]),
        (1, 0.10),
    ]


def parts(spec):
    import cadquery as cq

    section_checks(spec)
    p = spec["dimensions"]
    # Retain fixed drive/landing equipment; replace the geometry being optimized.
    equipment_parameters = {**p, "spar_diameter": min(p["spar_diameter"], 0.105 * p["root_chord"])}
    out = [
        o
        for o in legacy_parts(equipment_parameters)
        if not o["name"].startswith(("fuselage", "wing", "fin", "tail"))
    ]

    def add(name, shape, density, color, kind="structure", **extra):
        if not shape.isValid() or not shape.Solids() or shape.Volume() <= 0:
            raise ValueError(f"Invalid solid: {name}")
        out.append(dict(name=name, shape=shape, density=density, color=color, kind=kind, **extra))

    green, white, dark = (0.26, 0.43, 0.38), (0.79, 0.84, 0.79), (0.16, 0.20, 0.21)

    def hull(inner=False):
        wires = []
        for x, f in body_stations(spec):
            t = p["shell_thickness"] if inner else 0
            wires.append(
                cq.Workplane("YZ", origin=(x * p["fuselage_length"] * 1000, 0, 0))
                .ellipse(1000 * (p["fuselage_width"] * f / 2 - t), 1000 * (p["fuselage_height"] * f / 2 - t))
                .val()
            )
        return cq.Solid.makeLoft(wires, ruled=False)

    outer, inner = hull(), hull(True)
    add("fuselage", outer.cut(inner), 1150, green, cavity=inner, envelope=outer)
    wing_stations = stations(spec)
    for sign in (-1, 1):
        envelope = cq.Solid.makeLoft([wing_wire(s, sign) for s in wing_stations], ruled=False)
        outside, inside = [], []
        # Straight spar between root and tip; exact containment checks catch local pinching.
        for s in (wing_stations[0], wing_stations[-1]):
            a = math.radians(s["twist"])
            x, z = 0.25 * s["chord"], float(profile(s["section"]).local_camber(0.25)) * s["chord"]
            center = (
                1000 * (s["x"] + x * math.cos(a) + z * math.sin(a)),
                1000 * sign * s["y"],
                1000 * (s["z"] - x * math.sin(a) + z * math.cos(a)),
            )
            radius = 500 * p["spar_diameter"] * s["chord"] / p["root_chord"]
            outside.append(cq.Workplane("XZ", origin=center).circle(radius).val())
            inside.append(cq.Workplane("XZ", origin=center).circle(radius - p["spar_wall"] * 1000).val())
        spar = cq.Solid.makeLoft(outside, ruled=True).cut(cq.Solid.makeLoft(inside, ruled=True))
        add("wing_spar" + str(sign), spar, 2700, dark)
        add("wing" + str(sign), envelope.cut(spar).cut(outer), 32, white, "foam", envelope=envelope)
        # Root fillet fairing: smooth, low-density volume, trimmed against wing/body.
        # Build one canonical side and mirror it; identical root sections must not
        # acquire different boolean topology from opposite loft orientations.
        fairing_wires = [
            cq.Workplane("XZ", origin=(1000 * (p["wing_x"] + 0.40 * p["root_chord"]), -1000 * y, 80))
            .ellipse(1000 * p["root_chord"] * 0.60 * f, 34 * f)
            .val()
            for y, f in ((0, 1), (p["fuselage_width"] * 0.55, 0.9), (p["fuselage_width"] * 0.85, 0.08))
        ]
        fairing = (
            cq.Solid.makeLoft(fairing_wires, ruled=False)
            .cut(envelope if sign == -1 else envelope.mirror("XZ"), tol=0.001)
            .cut(outer, tol=0.001)
            .clean()
            .fix()
        )
        if sign == 1:
            fairing = fairing.mirror("XZ")
        add("root_fairing" + str(sign), fairing, 32, green, "foam")
        # Elliptical hollow covers enclose the existing circular structural booms.
        length = (p["rotor_rear_x"] - p["rotor_front_x"]) * 1000
        origin = (p["rotor_front_x"] * 1000, sign * p["boom_y"] * 1000, 90)
        cover = (
            cq.Workplane("YZ", origin=origin)
            .ellipse(p["boom_diameter"] * 850, p["boom_diameter"] * 600)
            .extrude(length)
            .val()
        )
        void = (
            cq.Workplane("YZ", origin=origin)
            .ellipse(p["boom_diameter"] * 850 - 1, p["boom_diameter"] * 600 - 1)
            .extrude(length)
            .val()
        )
        add("boom_fairing" + str(sign), cover.cut(void).cut(envelope), 1150, green)
    # Actual fin CAD and aerodynamic model share the same airfoil and section dimensions.
    import aerosandbox as a

    fin_section = a.Airfoil("naca0012").to_kulfan_airfoil()
    fdict = {k: np.asarray(getattr(fin_section, k)).tolist() for k in spec["root"]}
    for sign in (-1, 1):
        ts = [
            dict(x=p["tail_x"] + x, y=y, z=0.22, chord=c, twist=p["tail_incidence_deg"], section=fdict)
            for x, y, c in [(0, 0, p["tail_chord"]), (0.02, p["tail_span"] / 2, p["tail_chord"] * 0.7)]
        ]
        tail = cq.Solid.makeLoft([wing_wire(s, sign) for s in ts], ruled=False)
        add("tail" + str(sign), tail, 32, white, "foam")
    fs = [
        dict(x=p["fuselage_length"] * 0.78, y=0.03, z=0, chord=0.24, twist=0, section=fdict),
        dict(x=p["fuselage_length"] * 0.85, y=0.26, z=0, chord=0.17, twist=0, section=fdict),
    ]
    fin = cq.Solid.makeLoft([wing_wire(s, 1) for s in fs], ruled=False).rotate((0, 0, 0), (1, 0, 0), 90)
    add("fin", fin.cut(outer), 32, green, "foam")
    return out


def build(spec):
    import cadquery as cq

    a = cq.Assembly(name="streamlined_vtol")
    for o in parts(spec):
        a.add(o["shape"], name=o["name"], color=cq.Color(*o["color"]))
    return a
