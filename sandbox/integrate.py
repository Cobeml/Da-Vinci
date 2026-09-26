"""Independent shared-assembly validation from evaluated STEP artifacts."""

import json
from pathlib import Path

import cadquery as cq

spec = json.loads(Path("/input/specification.json").read_text())
mount = cq.importers.importStep("/input/structural.step")
surface = cq.importers.importStep("/input/aerodynamic.step")
mount = mount.translate(tuple(spec["assembly"]["mount_translation_mm"]))
violations = []
surface_solids = sorted(surface.solids().vals(), key=lambda s: s.Center().x)
mount_shape = mount.val()
for solid in surface_solids:
    if solid.intersect(mount_shape).Volume() > 0.001:
        violations.append({"code": "ASSEMBLY_COLLISION", "message": "Sensor mount intersects a surface body"})
if len(surface_solids) == 2:
    main, flap = surface_solids
    hinge = (main.BoundingBox().xmax + flap.BoundingBox().xmin) / 2
    for angle in spec["wing"]["travel_deg"]:
        moved = flap.rotate((hinge, 0, 0), (hinge, 1, 0), angle)
        if moved.intersect(mount_shape).Volume() > 0.001:
            violations.append(
                {
                    "code": "ASSEMBLY_TRAVEL_COLLISION",
                    "message": f"Surface intersects mount at {angle} degrees",
                }
            )
            break
mass = sum(s.Volume() for s in mount.solids().vals()) * 1e-9 * spec["material"]["density_kg_m3"]
mass += sum(s.Volume() for s in surface.solids().vals()) * 1e-9 * spec["wing"]["material_density_kg_m3"]
if mass > spec["assembly"]["max_mass_kg"]:
    violations.append({"code": "ASSEMBLY_MASS", "message": "Shared mass budget exceeded"})
assembly = cq.Assembly(name="shared_vehicle_components")
assembly.add(mount, name="sensor_mount", color=cq.Color(0.83, 0.49, 0.27))
assembly.add(surface, name="aerodynamic_surface", color=cq.Color(0.38, 0.7, 0.62))
assembly.export("/output/assembly.step")
assembly.export("/output/assembly.glb")
Path("/output/result.json").write_text(
    json.dumps({"outcome": "failed" if violations else "passed", "violations": violations, "mass_kg": mass})
)
