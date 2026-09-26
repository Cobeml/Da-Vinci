import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("utility", "/input/tool.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
request = json.loads(Path("/input/arguments.json").read_text())
result = module.run(request)
Path("/output/result.json").write_text(json.dumps(result, allow_nan=False))
