"""Untrusted code execution entry point. This container never produces scores."""

import importlib.util
import json
from pathlib import Path

root = Path("/input")
spec = importlib.util.spec_from_file_location("candidate", root / "source.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request = json.loads((root / "request.json").read_text())
assembly = module.build(request["parameters"], request["interfaces"])
assembly.export("/output/model.step")
