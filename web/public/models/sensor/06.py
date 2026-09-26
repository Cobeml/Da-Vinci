import cadquery as cq
from sensor_family import build_cradle


def build(parameters, interfaces) -> cq.Assembly:
    assembly = cq.Assembly(name="sensor_cradle")
    assembly.add(
        build_cradle(parameters),
        name="mount",
        color=cq.Color(0.9, 0.4, 0.14),
    )
    return assembly
