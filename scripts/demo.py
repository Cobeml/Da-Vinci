"""Run the full replay without the UI: .venv/bin/python -m scripts.demo."""

import argparse
import json
import time

from davinci.config import Settings
from davinci.engine import Engine
from davinci.models import RunRequest

parser = argparse.ArgumentParser()
parser.add_argument("--rounds", type=int, default=4)
args = parser.parse_args()
engine = Engine(Settings())
if not engine.runner.available():
    raise SystemExit("Build the image: docker compose --profile build build cad-image")
run = engine.start(RunRequest(rounds=args.rounds))
print(f"Started {run['_id']} (deterministic replay)", flush=True)
while engine.store.get("runs", run["_id"])["status"] == "running":
    engine.reconcile()
    job = engine.store.claim(seconds=600)
    if job:
        print(f"{job['kind']}: {job['subject_id']}", flush=True)
        engine.execute_job(job)
    else:
        time.sleep(0.5)
print(json.dumps(engine.store.get("runs", run["_id"]), indent=2))
