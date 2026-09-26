"""Graph-defined gripper geometry, three independently exported solids in millimetres."""
import math

import cadquery as cq

BASE_Z = 18.3
BASELINE = {
    "depth_mm": 24,
    "nodes": [[8, 0], [36, 0], [8, 70], [36, 70], [8, 35], [36, 35]],
    "edges": [[0, 4, 12], [4, 2, 12], [1, 5, 12], [5, 3, 12],
              [0, 1, 12], [4, 5, 12], [2, 3, 12], [0, 5, 12], [4, 3, 12]],
}


def validate(p):
    if set(p) != {"depth_mm", "nodes", "edges"}:
        raise ValueError("Expected depth_mm, nodes and edges")
    depth, nodes, edges = p["depth_mm"], p["nodes"], p["edges"]
    if not isinstance(depth, (float, int)) or not math.isfinite(depth) or not 10 <= depth <= 24:
        raise ValueError("Depth must be 10..24 mm")
    if not 3 <= len(nodes) <= 10 or nodes[:3] != [[8, 0], [36, 0], [8, 70]]:
        raise ValueError("Fixed root nodes 0,1 and contact node 2 required")
    for i, point in enumerate(nodes):
        if len(point) != 2 or not all(isinstance(v, (float, int)) and math.isfinite(v) for v in point):
            raise ValueError("Invalid node")
        x, z = point
        if not 8 <= x <= 40 or not (z == 0 if i < 2 else 12 <= z <= 70):
            raise ValueError("Node outside design envelope")
    if not 2 <= len(edges) <= 20:
        raise ValueError("Expected 2..20 ribs")
    seen, connected = set(), {0}
    for edge in edges:
        if len(edge) != 3:
            raise ValueError("Edge is [node_a,node_b,width_mm]")
        a, b, width = edge
        if not all(isinstance(v, (float, int)) and math.isfinite(v) for v in edge):
            raise ValueError("Nonfinite edge")
        if int(a) != a or int(b) != b or not 0 <= a < len(nodes) or not 0 <= b < len(nodes) or a == b:
            raise ValueError("Invalid edge endpoints")
        if not 3 <= width <= 12 or tuple(sorted((a, b))) in seen:
            raise ValueError("Invalid or duplicate rib")
        if math.dist(nodes[int(a)], nodes[int(b)]) < 10:
            raise ValueError("Member length must be >=10 mm")
        seen.add(tuple(sorted((a, b))))
    for _ in nodes:
        for a, b, _ in edges:
            if a in connected or b in connected:
                connected.update((a, b))
    if len(connected) != len(nodes):
        raise ValueError("All nodes must be connected to roots")


def base():
    plate = cq.Workplane("XY").box(220, 80, 8, centered=(True, True, False)).edges("|Z").fillet(5)
    plate = plate.faces(">Z").workplane().pushPoints([(-96, -34), (-96, 34), (96, -34), (96, 34)]).hole(5.5)
    for y in (-26, 26):
        plate = plate.union(cq.Workplane("XY").box(216, 8, 6).translate((0, y, 11)))
    for x in (-68, 0, 68):
        plate = plate.cut(cq.Workplane("XY").center(x, 0).slot2D(50, 24).extrude(10))
    return plate.clean()


def jaw(p):
    validate(p)
    depth, nodes = p["depth_mm"], p["nodes"]
    foot = cq.Workplane("XY").box(48, 70, 10, centered=(False, True, False)).translate((0, 0, -10))
    for y in (-26, 26):
        groove = cq.Workplane("XY").box(50, 8.6, 6.3, centered=(False, True, False)).translate((-1, y, -10))
        foot = foot.cut(groove)
    for y in (-16, 16):
        foot = foot.cut(cq.Workplane("XY").center(23, y).circle(2.25).extrude(-12))
    result = foot
    for a, b, width in p["edges"]:
        a, b = nodes[int(a)], nodes[int(b)]
        dx, dz = b[0]-a[0], b[1]-a[1]
        length = math.hypot(dx, dz)
        nx, nz = -dz/length*width/2, dx/length*width/2
        points = [(a[0]+nx, a[1]+nz), (b[0]+nx, b[1]+nz),
                  (b[0]-nx, b[1]-nz), (a[0]-nx, a[1]-nz)]
        rib = cq.Workplane("XZ").polyline(points).close().extrude(depth/2, both=True)
        for point in (a, b):
            rib = rib.union(cq.Workplane("XZ").center(*point).circle(width/2).extrude(depth/2, both=True))
        result = result.union(rib)
    pad = cq.Workplane("XY").box(8, 24, 20, centered=(False, True, False)).translate((0, 0, 60))
    return result.union(pad).clean().translate((0, 0, BASE_Z))


def parts(p, gap=60):
    right = jaw(p).translate((gap/2, 0, 0))
    left = jaw(p).mirror("YZ").translate((-gap/2, 0, 0))
    return {"base": base(), "right": right, "left": left}


def build_gripper(p):
    assembly = cq.Assembly(name="gripper")
    for name, part in parts(p).items():
        assembly.add(part, name=name, color=cq.Color(*((.65, .70, .65) if name == "base" else (.9, .4, .14))))
    return assembly
