"""Frozen VTOL family. Parameters use SI metres; exported CAD uses millimetres."""

import math

BASELINE = dict(
    span=2.1,
    root_chord=0.30,
    taper=0.75,
    twist_deg=-1.0,
    sweep=0.04,
    wing_x=0.30,
    fuselage_length=1.08,
    fuselage_width=0.19,
    fuselage_height=0.20,
    nose_fraction=0.25,
    tail_fraction=0.72,
    tail_span=0.72,
    tail_chord=0.17,
    tail_x=0.88,
    tail_incidence_deg=0.0,
    boom_y=0.46,
    rotor_front_x=0.13,
    rotor_rear_x=0.78,
    battery_x=0.28,
    payload_x=0.49,
    spar_diameter=0.025,
    spar_wall=0.0012,
    boom_diameter=0.020,
    boom_wall=0.001,
    shell_thickness=0.0015,
)
BOUNDS = dict(
    span=(1.6, 2.6),
    root_chord=(0.22, 0.40),
    taper=(0.5, 1),
    twist_deg=(-4, 0),
    sweep=(0, 0.12),
    wing_x=(0.23, 0.43),
    fuselage_length=(0.8, 1.4),
    fuselage_width=(0.14, 0.23),
    fuselage_height=(0.15, 0.24),
    nose_fraction=(0.18, 0.35),
    tail_fraction=(0.60, 0.78),
    tail_span=(0.5, 0.9),
    tail_chord=(0.12, 0.23),
    tail_x=(0.72, 1.15),
    tail_incidence_deg=(-3, 3),
    boom_y=(0.35, 0.60),
    rotor_front_x=(0.05, 0.23),
    rotor_rear_x=(0.70, 0.95),
    battery_x=(0.24, 0.50),
    payload_x=(0.36, 0.62),
    spar_diameter=(0.018, 0.035),
    spar_wall=(0.0008, 0.0018),
    boom_diameter=(0.016, 0.028),
    boom_wall=(0.0008, 0.0015),
    shell_thickness=(0.001, 0.002),
)


def validate(p):
    if set(p) != set(BOUNDS):
        raise ValueError("Use exactly the documented parameter keys")
    for k, (lo, hi) in BOUNDS.items():
        if (
            isinstance(p[k], bool)
            or not isinstance(p[k], (int, float))
            or not math.isfinite(p[k])
            or not lo <= p[k] <= hi
        ):
            raise ValueError(f"{k} must be finite in [{lo},{hi}]")
    if p["tail_x"] + p["tail_chord"] > p["fuselage_length"] + 0.14:
        raise ValueError("Tail trailing edge must remain near the fuselage tail")


def naca(code, chord, count=30):
    m, pos, t = int(code[0]) / 100, int(code[1]) / 10, int(code[2:]) / 100
    top = []
    bottom = []
    for i in range(count + 1):
        x = (1 - math.cos(math.pi * i / count)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x**3 - 0.1036 * x**4)
        yc = (
            0
            if not m
            else (
                m / pos**2 * (2 * pos * x - x * x)
                if x < pos
                else m / (1 - pos) ** 2 * ((1 - 2 * pos) + 2 * pos * x - x * x)
            )
        )
        dy = 0 if not m else (2 * m / pos**2 * (pos - x) if x < pos else 2 * m / (1 - pos) ** 2 * (pos - x))
        a = math.atan(dy)
        top.append(((x - yt * math.sin(a)) * chord, (yc + yt * math.cos(a)) * chord))
        bottom.append(((x + yt * math.sin(a)) * chord, (yc - yt * math.cos(a)) * chord))
    return top + bottom[-2:0:-1]


def parts(p):
    import cadquery as cq

    validate(p)
    s = {k: v * 1000 for k, v in p.items()}
    out = []

    def add(name, shape, density, color, kind="structure"):
        out.append(dict(name=name, shape=shape, density=density, color=color, kind=kind))

    green = (0.26, 0.43, 0.38)
    white = (0.79, 0.84, 0.79)
    dark = (0.16, 0.20, 0.21)
    orange = (0.95, 0.52, 0.22)
    length = s["fuselage_length"]
    w = s["fuselage_width"] / 2
    h = s["fuselage_height"] / 2
    t = s["shell_thickness"]
    stations = [
        (0, 0.04),
        (length * p["nose_fraction"], 1),
        (length * p["tail_fraction"], 0.84),
        (length, 0.12),
    ]

    def hull(inner=False):
        wires = []
        for x, f in stations:
            ry = max(w * f - (t if inner else 0), 1)
            rz = max(h * f - (t if inner else 0), 1)
            wires.append(cq.Workplane("YZ", origin=(x, 0, 0)).ellipse(ry, rz).val())
        return cq.Solid.makeLoft(wires, ruled=True)

    body = hull().cut(hull(True))
    add("fuselage", body, 1150, green)

    def wing(name, x, z, span, chord, taper, sweep, twist, code):
        for sign in (-1, 1):
            wires = []
            for frac in (0, 1):
                c = chord * (1 - frac + frac * taper)
                a = math.radians(twist * frac)
                pts = [
                    cq.Vector(
                        x + sweep * frac + xx * math.cos(a) + zz * math.sin(a),
                        sign * span / 2 * frac,
                        z - xx * math.sin(a) + zz * math.cos(a),
                    )
                    for xx, zz in naca(code, c)
                ]
                wires.append(cq.Wire.makePolygon(pts, close=True))
            add(name + str(sign), cq.Solid.makeLoft(wires, ruled=True), 32, white, "foam")

    wing("wing", s["wing_x"], 80, s["span"], s["root_chord"], p["taper"], s["sweep"], p["twist_deg"], "2412")
    wing("tail", s["tail_x"], 220, s["tail_span"], s["tail_chord"], 0.7, 20, 0, "0012")
    for o in out:
        if o["name"].startswith("tail"):
            o["shape"] = o["shape"].rotate(
                (s["tail_x"], 0, 220), (s["tail_x"], 1, 220), p["tail_incidence_deg"]
            )
    fin = (
        cq.Workplane("XZ")
        .polyline([(length * 0.78, 30), (length * 0.85, 260), (length + 50, 220), (length + 20, 20)])
        .close()
        .extrude(5, both=True)
        .val()
    )
    add("fin", fin, 40, green, "foam")

    def tube(name, start, end, dia, wall):
        a = cq.Vector(*start)
        b = cq.Vector(*end)
        axis = b - a
        outer = cq.Solid.makeCylinder(dia / 2, axis.Length, a, axis.normalized())
        inner = cq.Solid.makeCylinder(dia / 2 - wall, axis.Length, a, axis.normalized())
        add(name, outer.cut(inner), 2700, dark)

    tube(
        "wing_spar",
        (s["wing_x"] + 0.25 * s["root_chord"], -s["span"] / 2, 80),
        (s["wing_x"] + 0.25 * s["root_chord"], s["span"] / 2, 80),
        s["spar_diameter"],
        s["spar_wall"],
    )
    for sign in (-1, 1):
        y = sign * s["boom_y"]
        front = s["rotor_front_x"]
        rear = s["rotor_rear_x"]
        tube("boom" + str(sign), (front, y, 90), (rear, y, 90), s["boom_diameter"], s["boom_wall"])
        for x in (front, rear):
            add(f"motor_{sign}_{x}", cq.Solid.makeCylinder(24, 50, cq.Vector(x, y, 90)), 0, dark, "hardware")
            add(
                f"prop_{sign}_{x}",
                cq.Workplane("XY", origin=(x, y, 146)).box(406.4, 24, 4).val(),
                0,
                orange,
                "prop",
            )
        add(
            "skid" + str(sign),
            cq.Workplane("XY", origin=(length * 0.47, sign * 90, -h - 50)).box(340, 12, 10).val(),
            0,
            dark,
            "hardware",
        )
    add(
        "cruise_motor",
        cq.Solid.makeCylinder(26, 45, cq.Vector(-45, 0, 0), cq.Vector(1, 0, 0)),
        0,
        dark,
        "hardware",
    )
    add("cruise_prop", cq.Workplane("XY", origin=(-52, 0, 0)).box(4, 304.8, 25).val(), 0, orange, "prop")
    for name, x, dim, color in [
        ("battery", s["battery_x"], (150, 65, 60), orange),
        ("payload", s["payload_x"], (120, 100, 80), (0.3, 0.5, 0.8)),
    ]:
        add(name, cq.Workplane("XY", origin=(x, 0, -5)).box(*dim).val(), 0, color, "internal")
    # The foam shell mass excludes embedded spar material; structural masses are additive.
    spar = next(o["shape"] for o in out if o["name"] == "wing_spar")
    for o in out:
        if o["name"].startswith("wing") and o["kind"] == "foam":
            o["shape"] = o["shape"].cut(spar)
    return out


def build_vtol(p):
    import cadquery as cq

    assembly = cq.Assembly(name="survey_vtol")
    for o in parts(p):
        assembly.add(o["shape"], name=o["name"], color=cq.Color(*o["color"]))
    return assembly
