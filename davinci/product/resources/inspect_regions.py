"""Trusted independent STEP inspection. Never import candidate or evaluator code."""
import json
from pathlib import Path

import cadquery as cq

shape = cq.importers.importStep('/input/model.step')
solids = shape.solids().vals()
if not solids or any(not s.isValid() for s in solids):
    raise ValueError('Invalid solid geometry')
faces = []
for face in shape.faces().vals():
    if face.geomType() != 'PLANE':
        continue
    bb = face.BoundingBox()
    faces.append(dict(kind='PLANE', center=face.Center().toTuple(), normal=face.normalAt().toTuple(),
                      extent=[bb.xlen, bb.ylen, bb.zlen], area=face.Area()))
Path('/output/faces.json').write_text(json.dumps(faces, allow_nan=False))

request = json.loads(Path('/input/preparation.json').read_text())
scale = request['cad_to_solver_scale']
# CAD import remains in mm. This separate file is explicitly in declared solver units.
cq.exporters.export(shape.val().scale(scale), '/output/solver.step')
