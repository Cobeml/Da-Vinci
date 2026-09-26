import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("orchestration", "/input/orchestrator.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request = json.loads(Path("/input/request.json").read_text())
policy = json.loads(Path("/input/policy.json").read_text())
output = [module.adapt(case["parameters"], policy, case["subsystem"]) for case in request["cases"]]
Path("/output/result.json").write_text(json.dumps(output, allow_nan=False))
