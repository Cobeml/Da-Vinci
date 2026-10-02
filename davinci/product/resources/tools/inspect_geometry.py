"""Independent CAD inspection. Proposed source is absent from this sandbox."""

import json
from pathlib import Path

import cadquery as cq

items = []
for path in sorted(Path("/input").glob("model-*.step")):
    obj = cq.importers.importStep(str(path)).val()
    box = obj.BoundingBox()
    circles = []
    for edge in obj.Edges():
        if edge.geomType() == "CIRCLE":
            center = edge.arcCenter()
            circles.append([center.x, center.y, center.z, edge.radius()])
    items.append(
        dict(
            valid=obj.isValid(),
            solids=len(obj.Solids()),
            volume=obj.Volume(),
            bounds=[box.xmin, box.ymin, box.zmin, box.xmax, box.ymax, box.zmax],
            circles=circles,
        )
    )
Path("/output/measurements.json").write_text(
    json.dumps(dict(cadquery=cq.__version__, items=items), allow_nan=False)
)
