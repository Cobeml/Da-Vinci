"""Fresh-wheel test: public localhost routes, deterministic reasoning, real Docker CAD.

Run this script from /tmp with an interpreter that has the built wheel installed.
It does not import checkout modules or test fixtures and never calls a model API.
"""

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from importlib.resources import files
from pathlib import Path


def main():
    for key in list(os.environ):
        if key.startswith(("OPENAI_", "MONGODB_", "DAVINCI_")) or key == "PYTHONPATH":
            os.environ.pop(key, None)
    import uvicorn

    import davinci
    from davinci.config import Settings
    from davinci.product.api import create_app
    from davinci.product.client import Client
    from davinci.product.contracts import Candidate
    from davinci.product.engine import Engine
    from davinci.product.protocol import build_catalog, schema_catalog
    from davinci.product.recipes import EVALUATOR

    assert "site-packages" in Path(davinci.__file__).parts, "Use a fresh installed wheel, not a checkout"
    assert schema_catalog() == build_catalog()
    example = json.loads(files("davinci.product").joinpath("resources/managed/beam-example.json").read_text())
    assert files("davinci.product").joinpath("static/docs/product-journeys/index.html").is_file()
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    provider_calls = []

    class FixtureProvider:
        def __init__(self, engine, row):
            assert row["driver"] == "managed", "External execution must never construct a provider"

        def request(self, key, instruction, context):
            provider_calls.append(key)
            if context["stage"] == "requirements":
                return example["requirements"]
            if context["stage"] == "test_plan":
                return {
                    "plan": context["guidance"]["required_plan"],
                    "applicability_explanation": "Explicit beam fixture",
                }
            if context["stage"] == "setup":
                return {
                    "evaluator": {
                        "resources": {"evaluate.py": EVALUATOR},
                        "provenance": "Installed recipe fixture",
                    }
                }
            if context["stage"] == "propose":
                return Candidate(
                    title="Installed fixture",
                    source=context["guidance"]["builder_example"],
                    parameters={"thickness": 2 if not context["candidates"] else 4},
                ).model_dump()
            if context["stage"] == "diagnose":
                return {
                    "lesson": "Use independent measured margins",
                    "action": "design",
                    "explanation": "Preserve fixed loads and limits",
                }
            raise AssertionError(context["stage"])

    with tempfile.TemporaryDirectory(prefix="davinci-installed-routes-") as folder:
        root = Path(folder)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        (root / "workspace.yaml").write_text(f"port: {port}\nstorage: local\n")
        engine = Engine(
            root,
            provider=FixtureProvider,
            credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
        )
        server = uvicorn.Server(uvicorn.Config(create_app(root, engine=engine), log_level="error"))
        thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
        thread.start()
        try:
            for _ in range(200):
                if server.started:
                    break
                time.sleep(0.02)
            assert server.started
            client = Client(root)
            client.connect()
            start = client.request(
                "POST",
                "/api/v2/managed-experiments",
                {
                    "object": {"slug": "installed-beam", "name": "Installed beam"},
                    "description": example["description"],
                    "actor": "fixture",
                    "operation_id": "installed",
                    "mode": "replay",
                    "runtime": {
                        "image": image,
                        "solver": "NumPy beam",
                        "provenance": "Pinned installed-wheel check",
                    },
                    "policy": {"max_candidates": 2, "min_candidates": 2},
                },
            )
            eid = start["_id"]
            for _ in range(1200):
                row = client.status(eid)
                if row["managed"]["status"] != "ready":
                    break
                time.sleep(0.1)
            assert row["managed"]["status"] == "completed", row["managed"]
            measured = row["results"][-1]
            assert measured["design_accepted"] and measured["evidence_complete"]
            assert engine.artifacts.read(measured["artifacts"]["model.glb"])[:4] == b"glTF"
            count = len(provider_calls)
            other = client.request(
                "POST",
                f"/api/v2/experiments/{eid}/continue",
                {
                    "actor": row["actor"],
                    "revision": row["revision"],
                    "operation_id": "external",
                    "candidate_id": row["candidates"][-1]["id"],
                    "driver": "external",
                    "new_actor": "coder",
                },
            )
            xid = other["_id"]
            job = client.mutate(xid, "evaluate", {}, "evaluate")
            assert client.wait(xid, job["id"], 180)["status"] == "completed"
            result = client.status(xid)["results"][-1]
            assert result["suite_id"] == measured["suite_id"]
            assert result["candidate_version"] == measured["candidate_version"]
            for a, b in zip(result["tests"], measured["tests"]):
                for key, value in a["metrics"].items():
                    expected = b["metrics"][key]["value"]
                    assert abs(value["value"] - expected) <= max(1e-6, abs(expected) * 1e-8)
            client.mutate(
                xid, "reflections", {"lesson": "Reexecuted with same fixed test inputs"}, "reflection"
            )
            client.mutate(xid, "finalize", {}, "finalize")
            assert len(provider_calls) == count
            assert client.request("GET", f"/api/v2/experiments/{xid}/report")["report"][
                "accepted_candidate_ids"
            ]
            command = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "davinci.product.cli",
                    "--workspace",
                    folder,
                    "external",
                    "status",
                    xid,
                ],
                capture_output=True,
                text=True,
                check=True,
                cwd="/tmp",
            )
            assert json.loads(command.stdout)["data"]["phase"] == "completed"
            assert client.request("GET", "/api/v2/workspace/objects")[0]["iteration_count"] == 4
            print(
                json.dumps(
                    {
                        "fresh_wheel": True,
                        "checkout_imports": False,
                        "generation": "deterministic fixture",
                        "physics": "native CadQuery/OCP + NumPy analytic beam",
                        "managed_report": True,
                        "keyless_external_report": True,
                        "same_suite_parity": True,
                        "step_derived_glb": True,
                        "paid_calls": 0,
                    }
                )
            )
        finally:
            server.should_exit = True
            thread.join(30)
            sock.close()
            assert not thread.is_alive()


if __name__ == "__main__":
    main()
