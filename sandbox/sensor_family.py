"""Fixed sensor-cradle geometry contract, in millimetres."""

import math

import cadquery as cq

LIMITS = {
    "base_mm": (2.5, 7), "wall_mm": (2, 7), "window_mm": (0, 66),
    "window_style": (0, 2), "base_slots": (0, 3), "gusset_mm": (0, 16),
}


def validate(p):
    if set(p) != set(LIMITS):
        raise ValueError("Unexpected cradle parameters")
    for key, (low, high) in LIMITS.items():
        if not isinstance(p[key], (int, float)) or not math.isfinite(p[key]) or not low <= p[key] <= high:
            raise ValueError("Parameter outside geometry contract: " + key)
    for key in ("window_style", "base_slots"):
        if int(p[key]) != p[key]:
            raise ValueError(key + " must be an integer")
    if p["window_style"] and p["window_mm"] < 26:
        raise ValueError("Windows must be at least 26 mm long")


def build_cradle(p):
    validate(p)
    b, t = p["base_mm"], p["wall_mm"]
    base = cq.Workplane("XY").box(100, 72, b, centered=(True, True, False)).edges("|Z").fillet(5)
    base = base.faces(">Z").workplane().pushPoints([(-40, -26), (-40, 26), (40, -26), (40, 26)]).hole(4.5)
    slots = int(p["base_slots"])
    if slots:
        ys, width = {1: ([0], 32), 2: ([-12, 12], 14), 3: ([-19, 0, 19], 9)}[slots]
        for y in ys:
            cut = cq.Workplane("XY").center(0, y).slot2D(62, width).extrude(b + 2).translate((0, 0, -1))
            base = base.cut(cut)
    profile = [(-44, b - .2), (44, b - .2), (44, b + 24), (25, b + 42), (-25, b + 42), (-44, b + 24)]
    for sign in (-1, 1):
        y = sign * (32 - t / 2)
        wall = cq.Workplane("XZ").polyline(profile).close().extrude(t / 2, both=True).translate((0, y, 0))
        window = p["window_mm"]
        if p["window_style"] == 1:
            cut = cq.Workplane("XZ").center(0, b + 19).slot2D(window, 20).extrude(40, both=True)
            wall = wall.cut(cut)
        elif p["window_style"] == 2:
            low, high, half = b + 9, b + 29, window / 2
            for points in (
                [(-half, low), (half - 6, low), (-half, high)],
                [(-half + 6, high), (half, high), (half, low)],
            ):
                wall = wall.cut(cq.Workplane("XZ").polyline(points).close().extrude(40, both=True))
        axle = cq.Workplane("XZ").center(0, b + 35).circle(2.5).extrude(40, both=True)
        wall = wall.cut(axle)
        base = base.union(wall)
        h = p["gusset_mm"]
        if h:
            inner = sign * (32 - t)
            for x in (-34, 34):
                points = [(inner + sign * .2, b - .2), (inner - sign * 8, b - .2),
                          (inner + sign * .2, b + h)]
                rib = cq.Workplane("YZ").polyline(points).close().extrude(2, both=True).translate((x, 0, 0))
                base = base.union(rib)
    return base.clean()
