"""Public-route parity: same CAD source/parameters, frozen suite and pinned runtime."""

import os
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from test_external import ForbiddenProvider
from test_managed import engine_at, request

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.runner import Runner


def exercise(tmp_path, native):
    runner = None
    override = {}
    if native:
        image = subprocess.check_output(
            ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
        ).strip()
        runner = Runner(
            Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key="")
        )
        override["runtime"] = {
            "image": image,
            "solver": "CadQuery + NumPy",
            "provenance": "Native parity pinned runtime",
        }
    engine = engine_at(tmp_path, runner=runner)
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        r = client.post("/api/v2/managed-experiments", json=request(**override).model_dump())
        assert r.status_code == 202, r.text
        eid = r.json()["_id"]

        def status(id):
            return client.get("/api/v2/experiments/" + id).json()

        def wait(id, condition):
            for _ in range(1800):
                row = status(id)
                if condition(row):
                    return row
                assert row["phase"] not in ("interrupted", "cancelled"), row
                time.sleep(0.1)
            pytest.fail("Route did not complete within 180 seconds")

        managed = wait(eid, lambda x: x.get("managed", {}).get("status") in ("completed", "blocked"))
        assert managed["managed"]["status"] == "completed", managed["managed"]
        reference = managed["results"][-1]
        candidate = managed["candidates"][-1]
        engine.provider_type = ForbiddenProvider
        engine.credentials.openai_api_key = ""
        r = client.post(
            f"/api/v2/experiments/{eid}/continue",
            json={
                "actor": managed["actor"],
                "revision": managed["revision"],
                "operation_id": "external-parity",
                "candidate_id": candidate["id"],
                "driver": "external",
                "new_actor": "external-coder",
            },
        )
        assert r.status_code == 201, r.text
        external = r.json()
        xid = external["_id"]
        assert not external["results"]
        assert external["candidates"][0]["candidate_version"] == candidate["candidate_version"]

        def post(action, **payload):
            current = status(xid)
            r = client.post(
                f"/api/v2/experiments/{xid}/{action}",
                json={
                    "actor": current["actor"],
                    "revision": current["revision"],
                    "operation_id": action,
                    **payload,
                },
            )
            assert r.status_code < 300, r.text
            return r.json()

        post("evaluate")
        external = wait(xid, lambda x: x["phase"] == "evaluated")
        measured = external["results"][-1]
        for key in ("suite_id", "runtime_id", "plan_id", "evaluator_id", "execution_id", "candidate_version"):
            assert measured[key] == reference[key]
        assert measured["design_accepted"] == reference["design_accepted"]
        assert measured["evidence_complete"] == reference["evidence_complete"]
        for a, b in zip(measured["tests"], reference["tests"]):
            assert a["status"] == b["status"] and a["reason"] == b["reason"]
            for name, value in a["metrics"].items():
                assert value["unit"] == b["metrics"][name]["unit"]
                # Analytic recipe parity only; tolerance is not an accuracy guarantee for other physics.
                assert value["value"] == pytest.approx(b["metrics"][name]["value"], rel=1e-8, abs=1e-6)
        post(
            "reflections",
            lesson="Identical suite and runtime were reexecuted, not cached.",
            result_id=measured["id"],
        )
        post("finalize")
        report = client.get(f"/api/v2/experiments/{xid}/report").json()
        assert report["report"]["accepted_candidate_ids"]
        if native:
            assert engine.artifacts.read(measured["artifacts"]["model.step"]).startswith(b"ISO-10303")
        assert not engine.store.list("requests")


def test_fixture_route_parity(tmp_path):
    exercise(tmp_path, False)


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Explicit native CAD opt-in")
def test_native_route_parity(tmp_path):
    exercise(tmp_path, True)
