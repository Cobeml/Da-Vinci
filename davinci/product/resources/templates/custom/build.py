import cadquery as cq


def build(parameters, interfaces):
    a = cq.Assembly(name="plate_assembly")
    a.add(
        cq.Workplane("XY").box(interfaces["length_mm"], interfaces["width_mm"], parameters["thickness_mm"]),
        name="plate",
    )
    return a
