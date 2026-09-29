import json
from pathlib import Path

import cadquery as cq
from evaluate import evaluate

request = json.loads(Path("/input/request.json").read_text())
result = evaluate("/input/model.step", request["parameters"], request["specification"])
model = cq.importers.importStep("/input/model.step")
if not model.solids().vals() or not all(s.isValid() for s in model.solids().vals()):
    result["violations"].append({"code": "INVALID_SOLID", "message": "Invalid or empty STEP"})
    result["outcome"] = "failed"
assembly = cq.Assembly(name="component_assembly")
assembly.add(model, name="component", color=cq.Color(0.9, 0.4, 0.14))
assembly.export("/output/model.glb")
Path("/output/result.json").write_text(json.dumps(result, allow_nan=False))
