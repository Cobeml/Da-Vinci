"""Documented starting families. Live agents may rewrite source within the evaluator contract."""
MOUNT_SOURCE = '''import cadquery as cq

def build(parameters, interfaces):
    t = parameters["thickness_mm"]
    part = cq.Workplane("XY").box(80, 40, t)
    part = part.faces(">Z").workplane().pushPoints([(-30, -14), (-30, 14)]).hole(4)
    assembly = cq.Assembly(name="sensor_mount")
    assembly.add(part, name="mount", color=cq.Color(0.87, 0.48, 0.22))
    return assembly
'''

WING_SOURCE = '''import cadquery as cq
import math

def build(parameters, interfaces):
    span = parameters["span_mm"]
    chord = 120.0
    gap = parameters["hinge_gap_mm"]
    fraction = parameters["flap_fraction"]
    # Symmetric NACA thickness distribution, closed trailing edge, t/c = 0.12.
    def thickness(x):
        return 5 * 0.12 * chord * (0.2969 * math.sqrt(x) - 0.126*x - 0.3516*x*x + 0.2843*x**3 - 0.1036*x**4)
    xs = [(1 - math.cos(math.pi*i/60))/2 for i in range(61)]
    points = [(chord*x, thickness(x)) for x in xs]
    points += [(chord*x, -thickness(x)) for x in reversed(xs[1:-1])]
    body = cq.Workplane("XZ").polyline(points).close().extrude(span/2, both=True)
    hinge = chord * (1 - fraction)
    main = body.intersect(cq.Workplane("XY").box(hinge-gap/2, span+2, 100).translate(((hinge-gap/2)/2,0,0)))
    flap_length = chord-hinge-gap/2
    flap = body.intersect(cq.Workplane("XY").box(flap_length, span+2, 100).translate((hinge+gap/2+flap_length/2,0,0)))
    assembly = cq.Assembly(name="wing")
    assembly.add(main, name="main_surface", color=cq.Color(0.75, 0.80, 0.78))
    assembly.add(flap, name="control_surface", color=cq.Color(0.26, 0.63, 0.56))
    return assembly
'''

TOOL_SOURCE = '''import math

def run(arguments):
    # Orthographic projected area of an axis-aligned box. This is a geometric
    # proxy, not a drag coefficient or a model of an arbitrary mesh.
    x, y, z = arguments["dimensions_m"]
    direction = arguments["direction"]
    norm = math.sqrt(sum(v*v for v in direction))
    if min(x,y,z) <= 0 or norm == 0:
        raise ValueError("Positive dimensions and nonzero direction required")
    dx, dy, dz = [abs(v)/norm for v in direction]
    return {"projected_area_m2": y*z*dx + x*z*dy + x*y*dz,
            "fidelity": "bounding_box_proxy"}
'''

INITIAL_POLICY = {"minimum_mount_thickness_mm": 2.5, "minimum_hinge_gap_mm": 0.2,
                  "lessons": [], "retrieval_successes": 4, "retrieval_failures": 4}
INITIAL_ORCHESTRATOR = '''def adapt(parameters, policy, subsystem):
    return dict(parameters)
'''
IMPROVED_ORCHESTRATOR = '''def adapt(parameters, policy, subsystem):
    result = dict(parameters)
    if subsystem == "structural":
        result["thickness_mm"] = max(result["thickness_mm"], policy["minimum_mount_thickness_mm"])
    else:
        result["hinge_gap_mm"] = max(result["hinge_gap_mm"], policy["minimum_hinge_gap_mm"])
    return result
'''
INITIAL_UI = '''import React from "react";
export default function PolicyNote() {
  return <div style={{fontFamily:"monospace",color:"#a5ada7",padding:"12px"}}>BASELINE POLICY · Geometry screening active</div>;
}
'''
IMPROVED_UI = '''import React from "react";
export default function PolicyNote() {
  return <div style={{fontFamily:"monospace",color:"#8cd1bb",padding:"12px"}}>LEARNED POLICY · Thickness and hinge clearance checked before generation</div>;
}
'''
