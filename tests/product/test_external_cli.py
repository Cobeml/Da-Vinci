"""CLI talks to a real localhost service; no local lifecycle engine in the client."""

import json
import os
import socket
import subprocess
import sys
import threading
import time

import pytest
import uvicorn
from test_external import ForbiddenProvider
from test_simulation import SimulationRunner as FixtureRunner

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.cli import initialize
from davinci.product.engine import Engine


@pytest.fixture
def service(tmp_path, monkeypatch, request):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-key-must-not-be-used")
    monkeypatch.delenv("MONGODB_URI", raising=False)
    root = tmp_path / "workspace"
    initialize(root, "custom", driver="external")
    # Prebind to avoid the find-a-free-port race; uvicorn owns this socket below.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    (root / "workspace.yaml").write_text(f"storage: local\ndefault_driver: external\nport: {port}\n")
    engine = Engine(
        root,
        provider=ForbiddenProvider,
        runner=None if request.node.get_closest_marker("integration") else FixtureRunner(),
        credentials=Settings(_env_file=None, mongodb_uri=""),
    )
    server = uvicorn.Server(uvicorn.Config(create_app(root, engine=engine), log_level="error"))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]), daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.01)
    assert server.started
    yield root, engine
    server.should_exit = True
    thread.join(20)
    sock.close()
    assert not thread.is_alive()


def cli(root, *arguments):
    result = subprocess.run(
        [sys.executable, "-m", "davinci.product.cli", "--workspace", str(root), *arguments],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, json.loads(result.stdout)


def test_cli_public_contract_and_service_connection(service):
    root, engine = service
    code, health = cli(root, "service", "ensure")
    assert code == 0 and health["data"]["external_available"]
    code, doctor = cli(root, "doctor", "--driver", "external")
    assert code == 0 and not doctor["data"]["model_key_required"]
    code, adapters = cli(root, "external", "adapters")
    assert code == 0 and any(a["id"] == "authored-screen" for a in adapters["data"])
    code, schemas = cli(root, "external", "schemas")
    assert code == 0 and "CandidateCommand" in schemas["data"]["schemas"]
    code, opened = cli(root, "external", "open", "--file", str(root / "experiment.json"))
    assert code == 0
    eid = opened["data"]["_id"]
    code, repeat = cli(root, "external", "open", "--file", str(root / "experiment.json"))
    assert repeat["data"]["_id"] == eid
    code, state = cli(root, "external", "status", eid)
    assert state["data"]["next_actions"]
    code, frozen = cli(root, "external", "freeze", eid, "--operation-id", "too-early")
    assert code == 2 and not frozen["ok"]
    code, missing = cli(root, "external", "status", "missing")
    assert code == 5 and not missing["ok"]
    malformed = root / "bad.json"
    malformed.write_text("[]")
    code, invalid = cli(root, "external", "open", "--file", str(malformed))
    assert code == 2 and not invalid["ok"]
    malformed.write_text('{"lesson":"claim", "operation_id":"override"}')
    code, invalid = cli(
        root, "external", "reflect", eid, "--file", str(malformed), "--operation-id", "real-key"
    )
    assert code == 2 and "identity" in invalid["data"]["error"]
    assert not engine.store.list("requests")


def test_cli_idempotency_conflict_and_no_competing_writer(service):
    root, engine = service
    code, opened = cli(root, "external", "open", "--file", str(root / "experiment.json"))
    request = json.loads((root / "experiment.json").read_text())
    request["description"] = "A different payload using the same key"
    (root / "experiment.json").write_text(json.dumps(request))
    code, conflict = cli(root, "external", "open", "--file", str(root / "experiment.json"))
    assert code == 4
    assert "different" in conflict["data"]["error"]
    assert len(engine.store.list("runs")) == 1


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Requires Docker CAD image")
def test_real_cad_walkthrough_via_service_and_cli(service):
    root, engine = service
    completed = subprocess.run(
        [sys.executable, str(root / "external" / "walkthrough.py")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    eid = result["experiment_id"]
    code, results = cli(root, "external", "results", eid)
    assert code == 0
    first, second = results["data"]["results"]
    assert first["tests"][0]["status"] == "physical_failure"
    assert second["design_accepted"] and first["suite_id"] == second["suite_id"]
    assert (root / "external" / "candidate-0.step").read_bytes().startswith(b"ISO-10303")
    report_path = root / "export.json"
    code, exported = cli(root, "external", "report", eid, "--output", str(report_path))
    assert code == 0 and json.loads(report_path.read_text())["report"]["accepted_candidate_ids"]
    assert not engine.store.list("requests")
