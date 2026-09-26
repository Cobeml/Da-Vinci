"""Independent geometry contract for the supported NACA0012 extrusion family."""

import math

import cadquery as cq


def wing_reference(span, gap, fraction):
    chord = 120.0

    def thickness(x):
        return (
            5
            * 0.12
            * chord
            * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x**3 - 0.1036 * x**4)
        )

    xs = [(1 - math.cos(math.pi * i / 60)) / 2 for i in range(61)]
    points = [(chord * x, thickness(x)) for x in xs]
    points += [(chord * x, -thickness(x)) for x in reversed(xs[1:-1])]
    body = cq.Workplane("XZ").polyline(points).close().extrude(span / 2, both=True)
    hinge = chord * (1 - fraction)
    main = body.intersect(
        cq.Workplane("XY").box(hinge - gap / 2, span + 2, 100).translate(((hinge - gap / 2) / 2, 0, 0))
    )
    flap_length = chord - hinge - gap / 2
    flap = body.intersect(
        cq.Workplane("XY")
        .box(flap_length, span + 2, 100)
        .translate((hinge + gap / 2 + flap_length / 2, 0, 0))
    )
    return cq.Workplane("XY").newObject(
        [cq.Compound.makeCompound(main.solids().vals() + flap.solids().vals())]
    )
