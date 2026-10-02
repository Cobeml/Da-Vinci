"""Tool workflow orchestration fixtures and separately opted-in real CAD checks."""

import json
import math
import os
import subprocess
import time

import pytest
from fastapi.testclient import TestClient
from test_external import ForbiddenProvider, mutate, open_experiment, prepare
from test_lifecycle import IMAGE, FixtureRunner

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.engine import Engine
from davinci.product.resources.tools.plate_example import BROKEN, MISLEADING, SOURCE
from davinci.product.tool_contracts import PlateArguments
from davinci.product.tool_execution import check_source, references
from davinci.runner import Runner, SandboxError


class ToolFixtureRunner(FixtureRunner):
    """Deterministic protocol fixture. Never used as evidence for CAD correctness."""

    def execute(self, entry, files, **kwargs):
        if self.cancelled():
            raise SandboxError("cancelled", reason="cancelled")
        if entry == "/input/construct.py":
            return (
                {
                    f"model-{i}.step": json.dumps({"args": a, "source": files["helper.py"]}).encode()
                    for i, a in enumerate(json.loads(files["arguments.json"]))
                },
                "fixture construction",
                0,
            )
        if entry == "/input/inspect_geometry.py":
            items = []
            for name, raw in sorted(files.items()):
                if not name.endswith(".step"):
                    continue
                data = json.loads(raw)
                a = data["args"]
                x, y, z = a["translation"] if data["source"] != BROKEN else (0, 0, 0)
                sign = -1 if data["source"] == MISLEADING else 1
                items.append(
                    dict(
                        valid=True,
                        solids=1,
                        volume=(a["length"] * a["width"] - len(a["holes"]) * math.pi * a["radius"] ** 2)
                        * a["thickness"],
                        bounds=[
                            x - a["length"] / 2,
                            y - a["width"] / 2,
                            z,
                            x + a["length"] / 2,
                            y + a["width"] / 2,
                            z + a["thickness"],
                        ],
                        circles=[
                            [sign * i + x, sign * j + y, k, a["radius"]]
                            for i, j in a["holes"]
                            for k in (z, z + a["thickness"])
                        ],
                    )
                )
            return (
                {"measurements.json": json.dumps(dict(cadquery="2.8.0", items=items)).encode()},
                "fixture inspection",
                0,
            )
        return super().execute(entry, files, **kwargs)


def runtime(image=IMAGE):
    return dict(
        image=image,
        solver="CadQuery construction only",
        provenance="Pinned helper test runtime",
        cpu_cores=1,
        memory_gb=2,
        timeout_seconds=60,
        job_seconds=120,
        compute_seconds=120,
        artifact_bytes=16_000_000,
        file_bytes=8_000_000,
    )


class Session:
    def __init__(self, client, tid):
        self.client, self.tid = client, tid
        self.sequence = 0

    def get(self):
        return self.client.get("/api/v2/tools/" + self.tid).json()

    def post(self, action, *, actor=None, expect=200, **payload):
        row = self.get()
        self.sequence += 1
        body = dict(
            actor=actor or row["actor"],
            revision=row["revision"],
            operation_id=f"op-{self.sequence}",
            **payload,
        )
        response = self.client.post(f"/api/v2/tools/{self.tid}/{action}", json=body)
        assert response.status_code == expect, response.text
        return response.json()

    def wait(self):
        until = time.monotonic() + 180
        while time.monotonic() < until:
            row = self.get()
            if row["phase"] not in ("queued", "running"):
                return row
            time.sleep(0.02)
        pytest.fail("Tool job timed out")

    def propose_check(self, source, parent=None):
        row = self.post(
            "propose", source=source, summary="Tested placement correction", parent_version=parent
        )
        vid = row["versions"][-1]["id"]
        self.post("check", version_id=vid, expect=202)
        return self.wait(), vid


def opened(client, eid, image=IMAGE, actor="coding-agent", name="plate-layout"):
    r = client.post(
        "/api/v2/tools",
        json=dict(
            actor=actor,
            operation_id="need-" + name,
            experiment_id=eid,
            name=name,
            need="Repeated plate holes lose their placement transform",
            observations=["Asymmetric translated fixtures reproduce missing placement"],
        ),
    )
    assert r.status_code == 201, r.text
    s = Session(client, r.json()["_id"])
    s.post(
        "define",
        runtime=runtime(image),
        applicability="Rectangular mm plates, disjoint circular through holes, no structural certification",
    )
    return s


def another_object(client, operation, driver="external"):
    response = client.post(
        "/api/v2/experiments",
        json=dict(
            object={"slug": operation, "name": operation},
            description="Reuse the positioned plate construction helper while preserving independent tests",
            actor="coding-agent",
            operation_id=operation,
            driver=driver,
            mode="replay" if driver == "managed" else "live",
        ),
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef run(a):\n return os.system('true')",
        "import cadquery as cq\ndef run(a):\n open('/output/result.json','w')\n return cq.Workplane('XY')",
        "import cadquery as cq\ndef run(a):\n return cq.__dict__",
        "import cadquery as cq\ndef run(a):\n return cq.exporters.export(a,'/output/fake')",
    ],
)
def test_tool_capability_boundary(source):
    with pytest.raises(ValueError):
        check_source(source)


def test_tool_arguments_units_and_overlap():
    check_source(SOURCE)
    check_source(MISLEADING)
    for a in [
        dict(references()[0], unit="m"),
        dict(references()[0], holes=[[0, 0], [0, 0]]),
        dict(references()[0], translation=[float("nan"), 0, 0]),
    ]:
        with pytest.raises(ValueError):
            PlateArguments.model_validate(a)


def test_public_tool_workflow(tmp_path):
    engine = Engine(
        tmp_path,
        runner=ToolFixtureRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key="present-but-never-used"),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        first = prepare(client, open_experiment(client))
        s = opened(client, first["_id"])
        assert s.post(
            "define",
            runtime=runtime(),
            applicability="Cannot replace independent checks after definition",
            expect=409,
        )
        row, bad = s.propose_check(BROKEN)
        assert row["versions"][-1]["status"] == "rejected"
        assert any(not c["checks"]["bounds"] for c in row["job"]["checks"])
        row, good = s.propose_check(SOURCE, bad)
        assert row["versions"][-1]["status"] == "tested"
        s.post("promote", version_id=good, reason="All independent construction regressions passed")

        def pin(run, version, **overrides):
            current = client.get("/api/v2/experiments/" + run["_id"]).json()
            return client.post(
                f"/api/v2/experiments/{run['_id']}/tool-pins",
                json=dict(
                    actor=current["actor"],
                    revision=current["revision"],
                    operation_id="pin-" + version,
                    development_id=s.tid,
                    version_id=version,
                    contract_id=s.get()["contract_id"],
                    **overrides,
                ),
            )

        assert pin(first, good).status_code == 200
        s.post("invoke", experiment_id=first["_id"], arguments=references()[1], expect=202)
        used = s.wait()
        assert used["job"]["passed"]
        bundle = client.get(f"/api/v2/tools/{s.tid}/bundles/{used['job']['id']}").json()
        assert "def build" in bundle["source"] and bundle["metadata"]["tool_version_id"] == good
        unchanged = client.get("/api/v2/experiments/" + first["_id"]).json()
        assert unchanged["suite_id"] == first["suite_id"] and unchanged["results"] == first["results"]
        assert unchanged["plan"] == first["plan"] and unchanged["evaluator"] == first["evaluator"]
        row, misleading = s.propose_check(MISLEADING, good)
        assert row["versions"][-1]["status"] == "rejected"
        assert all(c["checks"]["analytic_volume"] for c in row["job"]["checks"])
        assert any(not c["checks"]["hole_edges"] for c in row["job"]["checks"])
        s.post(
            "promote", version_id=misleading, reason="Should never activate incorrect geometry", expect=409
        )
        row, second = s.propose_check(SOURCE + "\n# equivalent reviewed revision\n", good)
        assert row["job"]["passed"]
        s.post(
            "promote", version_id=second, reason="Reference and regression checks passed for this revision"
        )
        assert (
            client.get("/api/v2/experiments/" + first["_id"]).json()["tool_pins"][s.tid]["version_id"] == good
        )
        later = prepare(client, another_object(client, "later-object"))
        assert pin(later, second).status_code == 200
        s.post("invoke", experiment_id=later["_id"], arguments=references()[2], expect=202)
        assert s.wait()["job"]["passed"]
        s.post(
            "rollback",
            version_id=second,
            reason="Explicit conservative rollback after a suspected new defect",
        )
        assert s.get()["active_version"] == good
        s.post("invoke", experiment_id=later["_id"], arguments=references()[2], expect=409)
        s.post("invoke", experiment_id=first["_id"], arguments=references()[3], expect=202)
        assert s.wait()["job"]["passed"]
        # Re-pinning an active run is forbidden even to another tested version.
        current = client.get("/api/v2/experiments/" + later["_id"]).json()
        r = client.post(
            f"/api/v2/experiments/{later['_id']}/tool-pins",
            json=dict(
                actor=current["actor"],
                revision=current["revision"],
                operation_id="change-pin",
                development_id=s.tid,
                version_id=good,
                contract_id=s.get()["contract_id"],
            ),
        )
        assert r.status_code == 409
        memory = client.post("/api/v2/memory/search", json={"query": "plate helper"}).json()
        assert memory["items"]
        assert not engine.store.list("requests")


def test_tool_order_idempotency_cancel_restart_and_scope(tmp_path):
    engine = Engine(
        tmp_path,
        runner=ToolFixtureRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
    )
    with TestClient(create_app(tmp_path, engine=engine, run_worker=False)) as client:
        run = open_experiment(client)
        s = opened(client, run["_id"])
        row = s.post("propose", source=SOURCE, summary="Initial source")
        body = dict(
            actor=row["actor"],
            revision=row["revision"],
            operation_id="check-idempotent",
            version_id=row["versions"][-1]["id"],
        )
        path = "/api/v2/tools/" + s.tid + "/check"
        r = client.post(path, json=body)
        assert r.status_code == 202
        assert client.post(path, json=body).json()["job"]["id"] == r.json()["job"]["id"]
        assert client.post(path, json={**body, "version_id": "different"}).status_code == 409
        s.post("cancel")
        engine.tool_learning.execute_scheduled(s.tid)
        assert s.get()["phase"] == "cancelled"
        s.post("check", version_id=body["version_id"], expect=202)
        engine.recover()
        assert s.get()["phase"] == "interrupted"
        s.post("check", version_id=body["version_id"], expect=202)
        engine.tool_learning.execute_scheduled(s.tid)
        assert s.get()["job"]["passed"]
        s.post(
            "promote", version_id=body["version_id"], reason="Verified after explicit interrupted job retry"
        )
        r = client.post(
            f"/api/v2/experiments/{run['_id']}/tool-pins",
            json=dict(
                actor=run["actor"],
                revision=run["revision"],
                operation_id="too-early",
                development_id=s.tid,
                version_id=body["version_id"],
                contract_id=s.get()["contract_id"],
            ),
        )
        assert r.status_code == 409
        # Caller-supplied evidence fields cannot become trusted checks.
        r = client.post(path, json={**body, "passed": True, "results": {"design_accepted": True}})
        assert r.status_code == 422
        assert s.post("propose", source=SOURCE, summary="Wrong owner", actor="intruder", expect=409)
        engine.options.project_id = "different"
        engine.experience.scope["project_id"] = "different"
        assert client.get("/api/v2/tools/" + s.tid).status_code == 404


def test_managed_tool_author_uses_same_service_and_external_rejected(tmp_path):
    calls = []

    class ProviderFixture:
        def __init__(self, engine, row):
            assert row["driver"] == "managed"

        def request(self, key, instruction, context):
            calls.append(key)
            assert context["contract"]["reference_cases"] == references()
            return {"source": SOURCE, "summary": "Preserve translated and asymmetric hole patterns"}

    engine = Engine(
        tmp_path,
        runner=ToolFixtureRunner(),
        provider=ProviderFixture,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        managed = prepare(client, another_object(client, "managed-tool", "managed"))
        s = opened(client, managed["_id"])
        command = dict(
            actor=managed["actor"],
            revision=managed["revision"],
            operation_id="generate",
            development_id=s.tid,
            tool_revision=s.get()["revision"],
        )
        path = f"/api/v2/experiments/{managed['_id']}/tool-proposals"
        r = client.post(path, json=command)
        assert r.status_code == 200, r.text
        assert client.post(path, json=command).status_code == 200
        assert len(calls) == 1
        vid = s.get()["versions"][-1]["id"]
        s.post("check", version_id=vid, expect=202)
        assert s.wait()["job"]["passed"]
        s.post("promote", version_id=vid, reason="Independent geometry checks passed for managed proposal")
        mutate(
            client,
            managed["_id"],
            "tool-pins",
            "pin",
            dict(development_id=s.tid, version_id=vid, contract_id=s.get()["contract_id"]),
        )
        s.post("invoke", experiment_id=managed["_id"], arguments=references()[1], expect=202)
        assert s.wait()["job"]["passed"]
        assert client.get(f"/api/v2/experiments/{managed['_id']}").json()["suite_id"] == managed["suite_id"]
        external = another_object(client, "external-no-generation")
        assert (
            client.post(
                f"/api/v2/experiments/{external['_id']}/tool-proposals",
                json={**command, "revision": external["revision"]},
            ).status_code
            == 409
        )
        assert len(calls) == 1


def test_incompatible_tool_and_forged_score_protection(tmp_path, monkeypatch):
    engine = Engine(
        tmp_path,
        runner=ToolFixtureRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        run = prepare(client, open_experiment(client))
        s = opened(client, run["_id"])
        row, bad = s.propose_check(
            "import cadquery as cq\ndef run(a):\n open('/input/suite.json','w')\n return cq.Workplane('XY')"
        )
        assert row["job"]["reason"] == "policy_or_contract_rejected"
        row, good = s.propose_check(SOURCE, bad)
        assert row["job"]["passed"]
        s.post("promote", version_id=good, reason="Independent checks passed")
        current = client.get("/api/v2/experiments/" + run["_id"]).json()
        pin = dict(
            actor=current["actor"],
            revision=current["revision"],
            operation_id="pin",
            development_id=s.tid,
            version_id=good,
            contract_id="wrong-contract",
        )
        path = f"/api/v2/experiments/{run['_id']}/tool-pins"
        assert client.post(path, json=pin).status_code == 409
        monkeypatch.setattr(
            "davinci.product.tool_learning.implementation_identity", lambda: "changed-trusted-runtime"
        )
        assert client.post(path, json={**pin, "contract_id": s.get()["contract_id"]}).status_code == 409
        after = client.get("/api/v2/experiments/" + run["_id"]).json()
        assert after["plan"] == run["plan"] and after["results"] == []


def test_running_tool_cancellation_and_resource_failure(tmp_path):
    import threading

    entered = threading.Event()

    class Blocking(ToolFixtureRunner):
        fail = False

        def execute(self, entry, files, **kwargs):
            if entry == "/input/construct.py":
                if self.fail:
                    raise SandboxError("Fixture output quota exhausted", reason="artifact_quota")
                entered.set()
                while not self.cancelled():
                    time.sleep(0.01)
                raise SandboxError("Cancelled fixture execution", reason="cancelled")
            return super().execute(entry, files, **kwargs)

    runner = Blocking()
    engine = Engine(
        tmp_path,
        runner=runner,
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        run = open_experiment(client)
        s = opened(client, run["_id"])
        row = s.post("propose", source=SOURCE, summary="Cancel during construction")
        vid = row["versions"][-1]["id"]
        s.post("check", version_id=vid, expect=202)
        assert entered.wait(5)
        s.post("cancel")
        deadline = time.monotonic() + 5
        while engine.busy and time.monotonic() < deadline:
            time.sleep(0.02)
        assert not engine.busy and s.get()["job"]["reason"] == "cancelled"
        assert s.get()["versions"][-1]["status"] == "proposed"
        runner.fail = True
        s.post("check", version_id=vid, expect=202)
        assert s.wait()["job"]["reason"] == "artifact_quota"
        assert s.get()["versions"][-1]["status"] == "rejected"


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("DAVINCI_INTEGRATION") != "1", reason="Explicit native CAD tool checks")
def test_native_tool_defect_revision_and_reuse(tmp_path):
    image = subprocess.check_output(
        ["docker", "image", "inspect", "--format={{.Id}}", "da-vinci-cad:local"], text=True
    ).strip()
    # Only lifecycle setup uses the deterministic fixture. Every helper execution and
    # independent STEP inspection below uses actual CadQuery in separate containers.
    real = Runner(Settings(_env_file=None, davinci_data_dir=tmp_path, mongodb_uri="", openai_api_key=""))

    class MixedRunner(ToolFixtureRunner):
        def execute(self, entry, files, **kwargs):
            if entry in ("/input/construct.py", "/input/inspect_geometry.py"):
                real.cancelled = self.cancelled
                return real.execute(entry, files, **kwargs)
            return super().execute(entry, files, **kwargs)

    engine = Engine(
        tmp_path,
        runner=MixedRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, mongodb_uri="", openai_api_key=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        first = prepare(client, open_experiment(client))
        s = opened(client, first["_id"], image=image)
        row, broken = s.propose_check(BROKEN)
        assert row["job"]["reason"] == "checks_failed", row["job"]
        row, good = s.propose_check(SOURCE, broken)
        assert row["job"]["passed"], row["job"]
        s.post(
            "promote", version_id=good, reason="Actual CAD reference and placement regression checks passed"
        )
        row, wrong = s.propose_check(MISLEADING, good)
        assert row["job"]["reason"] == "checks_failed", row["job"]
        assert all(c["checks"]["analytic_volume"] for c in row["job"]["checks"])
        for i in range(2):
            later = prepare(client, another_object(client, "reuse-" + str(i)))
            mutate(
                client,
                later["_id"],
                "tool-pins",
                "pin",
                dict(development_id=s.tid, version_id=good, contract_id=s.get()["contract_id"]),
            )
            s.post("invoke", experiment_id=later["_id"], arguments=references()[i + 1], expect=202)
            used = s.wait()
            assert used["job"]["passed"], used["job"]
            aid = used["job"]["artifacts"]["built-model-0.step"]
            assert client.get("/api/v1/artifacts/" + aid).content.startswith(b"ISO-10303")
        (tmp_path / "tool-evidence.json").write_text(json.dumps(s.get(), indent=2))
