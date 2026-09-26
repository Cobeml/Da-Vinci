"""Explicit, resumable Atlas validation; never run by ordinary pytest collection."""

import argparse
import fcntl
import hashlib
import io
import json
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from davinci.artifacts import Artifacts
from davinci.budget import Budget, BudgetExceeded
from davinci.config import Settings
from davinci.engine import Engine
from davinci.models import SPECIFICATION, PatchProposal, RunRequest, document, now

SESSION = "atlas-validation-20260926"
ALLOCATIONS = {"live1": 10, "live2": 10, "live3": 5}


def emit(**data):
    print(json.dumps(data), flush=True)


class Validation:
    def __init__(self):
        self.settings = Settings()
        if not self.settings.mongodb_uri:
            raise RuntimeError("Atlas is not configured")
        self.root = self.settings.root / "validation"
        self.root.mkdir(exist_ok=True)
        self.lock = (self.root / "session.lock").open("a")
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.engine = Engine(self.settings)
        self.store = self.engine.store
        self.store.insert(
            "validations",
            {
                "_id": SESSION,
                "revision": 0,
                "created_at": now(),
                "allocations": ALLOCATIONS,
                "runs": {},
                "checks": {},
            },
        )
        if self.record()["allocations"] != ALLOCATIONS:
            raise RuntimeError("Validation allocation mismatch")

    def record(self):
        return self.store.get("validations", SESSION)

    def save(self, name, **result):
        result = {"checked_at": now(), **result}

        def update(doc):
            doc["checks"][name] = result
            return doc

        self.store.mutate("validations", SESSION, update)
        (self.root / "report.json").write_text(json.dumps(self.record(), indent=2))
        emit(stage=name, **result)

    def infrastructure(self):
        payload = b"Da Vinci Atlas GridFS validation\n"
        artifact = self.engine.artifacts.put(payload, "validation.txt", "text/plain", validation=SESSION)
        with tempfile.TemporaryDirectory(dir=self.root) as empty:
            downloaded = Artifacts(empty, self.store).read(artifact)
        assert downloaded == payload
        index = next(i for i in self.store.db.memories.list_search_indexes() if i["name"] == "memory_vector")
        assert index["queryable"] and index["status"] == "READY"
        assert index["latestDefinition"]["fields"][0]["numDimensions"] == 1536
        self.save(
            "infrastructure",
            passed=True,
            gridfs_remote_read=True,
            artifact_id=artifact,
            sha256=hashlib.sha256(downloaded).hexdigest(),
            vector_index_ready=True,
        )

    def prepare(self):
        directory = self.root / "triggers"
        directory.mkdir(exist_ok=True)
        for name in ("enqueue-candidate.js", "enqueue-reflection.js"):
            source = (
                (Path("atlas") / name)
                .read_text()
                .replace('context.values.get("DAVINCI_DATABASE")', json.dumps(self.settings.mongodb_database))
                .replace(
                    'context.services.get("mongodb-atlas")',
                    "context.services.get(" + json.dumps(self.settings.davinci_atlas_service) + ")",
                )
            )
            (directory / name).write_text(source)
        self.save(
            "trigger_sources",
            passed=True,
            directory=str(directory),
            database=self.settings.mongodb_database,
            linked_service=self.settings.davinci_atlas_service,
        )

    def recovery(self):
        assert not self.store.list("runs", {"status": "running"}), (
            "Run recovery checks while workers are stopped"
        )
        run_id = document("recovery-probe")["_id"]
        self.store.insert(
            "runs",
            document(
                "run",
                _id=run_id,
                status="running",
                mode="replay",
                phase="generating",
                round=0,
                diagnostic=True,
                budget_usd=0.05,
                spent_usd=0,
                revision=0,
            ),
        )
        try:
            self.engine.reconcile()
            job_id = "generate_round:" + run_id + ":0"
            assert self.store.get("jobs", job_id)
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(lambda _: self.store.claim(), range(2)))
            claimed = [job for job in claims if job]
            assert len(claimed) == 1 and claimed[0]["_id"] == job_id
            old = claimed[0]
            self.store.update("jobs", job_id, {"lease_expires_at": "2000-01-01T00:00:00+00:00"})
            restarted = Engine(self.settings)
            new = restarted.store.claim()
            assert new["lease_token"] != old["lease_token"]
            assert self.store.finish(old) is None
            budget = Budget(self.store, self.settings.davinci_daily_budget_usd)
            reservation = budget.reserve(run_id, 0.04)
            try:
                budget.reserve(run_id, 0.02)
            except BudgetExceeded:
                pass
            else:
                raise AssertionError("Budget should refuse excess reservation")
            budget.settle(reservation, 0)
            restarted.stop(run_id)
            restarted.execute_job(new)
            assert self.store.get("jobs", job_id)["status"] == "cancelled"
            self.save(
                "recovery",
                passed=True,
                diagnostic_run_id=run_id,
                concurrent_claim=True,
                stale_lease_rejected=True,
                reconciler_created_job=True,
                restart=True,
                cancellation=True,
                budget_exhaustion=True,
            )
        finally:
            self.engine.stop(run_id)

    def triggers(self):
        # Operators stop all workers before this stage. No Engine.reconcile or
        # Store.enqueue is called here: only Atlas triggers can create these jobs.
        attempt = document("trigger-probe")["_id"]
        run_id = attempt + "-run"
        self.store.insert(
            "runs",
            document(
                "run",
                _id=run_id,
                status="completed",
                mode="replay",
                diagnostic=True,
                validation_session=SESSION,
            ),
        )
        candidate_id, evaluation_id = attempt + "-candidate", attempt + "-evaluation"
        self.store.insert(
            "candidates",
            document(
                "candidate",
                _id=candidate_id,
                run_id=run_id,
                project_id="validation-diagnostic",
                source_commit="diagnostic-no-code",
                source_bundle_artifact_id="diagnostic-no-artifact",
                specification_id=SPECIFICATION["_id"],
                parameters={},
                subsystem="structural",
                diagnostic=True,
            ),
        )
        self.store.insert(
            "evaluations",
            document(
                "evaluation",
                _id=evaluation_id,
                candidate_id=candidate_id,
                run_id=run_id,
                evaluator_version="trigger-diagnostic",
                outcome="failed",
                metrics={},
                violations=[],
                diagnostic=True,
            ),
        )
        ids = ["evaluate_candidate:" + candidate_id, "reflect_on_evaluation:" + evaluation_id]
        deadline = time.monotonic() + 120
        while not all(self.store.get("jobs", job_id) for job_id in ids):
            if time.monotonic() >= deadline:
                self.save(
                    "triggers",
                    passed=False,
                    reason="delivery_timeout",
                    diagnostic_run_id=run_id,
                    observed_jobs=[
                        {"kind": j["kind"], "subject_id": j["subject_id"]}
                        for j in self.store.list("jobs", {"run_id": run_id})
                    ],
                )
                return False
            time.sleep(2)
        assert all(self.store.db.jobs.count_documents({"_id": job_id}) == 1 for job_id in ids)
        self.save("triggers", passed=True, workers_stopped=True, job_ids=ids, diagnostic_run_id=run_id)
        return True

    def run(self, slot, rounds):
        run_id = f"run-{SESSION}-{slot}"
        allocation = ALLOCATIONS.get(slot, 0)

        # Reserve each named allocation before starting. Deterministic run IDs
        # prevent a crash between start and checkpoint from creating another run.
        def reserve(doc):
            doc["runs"].setdefault(slot, {"run_id": run_id, "budget_usd": allocation})
            return doc

        self.store.mutate("validations", SESSION, reserve)
        request = RunRequest(
            mode="replay" if slot == "replay" else "live", rounds=rounds, budget_usd=allocation or 1
        )
        run = self.engine.start(request, run_id=run_id)
        emit(stage="run_started", slot=slot, run_id=run_id, budget_usd=run["budget_usd"])
        return run_id

    def monitor(self, slot, seconds):
        run_id = self.record()["runs"][slot]["run_id"]
        deadline = time.monotonic() + seconds
        previous = None
        while True:
            run = self.store.get("runs", run_id)
            state = (run["status"], run["round"], run["phase"], round(run["spent_usd"], 5))
            if state != previous:
                emit(
                    stage="run_progress",
                    slot=slot,
                    status=state[0],
                    round=state[1],
                    phase=state[2],
                    spent_usd=state[3],
                )
                previous = state
            if run["status"] != "running":
                break
            if time.monotonic() >= deadline:
                self.engine.stop(run_id)
                self.save(slot, passed=False, reason="validation_timeout", run_id=run_id)
                return False
            time.sleep(5)
        evaluations = self.store.list("evaluations", {"run_id": run_id})
        self.save(
            slot,
            passed=run["status"] == "completed",
            run_id=run_id,
            status=run["status"],
            spent_usd=run["spent_usd"],
            evaluations=len(evaluations),
            passed_evaluations=sum(e["outcome"] == "passed" for e in evaluations),
            accepted_assemblies=len(self.store.list("champions", {"run_id": run_id})),
        )
        return run["status"] == "completed"

    def vector(self, slot):
        run_id = self.record()["runs"][slot]["run_id"]
        run = self.store.get("runs", run_id)
        provider = self.engine.provider(run)
        # Include known pass/fail replay evidence, keeping its original provenance.
        memories = self.store.list("memories", {"evaluator_version": self.engine.evaluator_version})
        for memory in memories:
            if memory.get("embedding_status") != "ready":
                embedding = provider.embed(memory["summary"], run_id)
                assert len(embedding) == 1536
                self.store.update(
                    "memories",
                    memory["_id"],
                    {
                        "embedding": embedding,
                        "embedding_status": "ready",
                        "embedding_validation_run_id": run_id,
                    },
                )
        vector = provider.embed("structural mount thickness failures and successful clearance", run_id)
        deadline = time.monotonic() + 120
        outcomes = {m["outcome"] for m in memories}
        hits = []
        while True:
            hits = list(
                self.store.db.memories.aggregate(
                    [
                        {
                            "$vectorSearch": {
                                "index": "memory_vector",
                                "path": "embedding",
                                "queryVector": vector,
                                "numCandidates": 100,
                                "limit": 20,
                                "filter": {
                                    "project_id": "uas-demo",
                                    "specification_id": SPECIFICATION["_id"],
                                    "evaluator_version": self.engine.evaluator_version,
                                    "embedding_version": 1,
                                },
                            }
                        },
                        {"$project": {"_id": 1, "outcome": 1, "score": {"$meta": "vectorSearchScore"}}},
                    ]
                )
            )
            if hits and outcomes.issubset({h["outcome"] for h in hits}):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("Vector results not visible")
            time.sleep(3)
        selected = self.engine.memory(run).search("structural", "thin mount failure", run_id=run_id)
        assert any(m.get("semantic_score") is not None for m in selected)
        assert all(
            m["subsystem"] == "structural"
            and m["specification_id"] == SPECIFICATION["_id"]
            and m["evaluator_version"] == self.engine.evaluator_version
            for m in selected
        )
        self.save("vector", passed=True, direct_hits=hits, scoped_memory_ids=[m["_id"] for m in selected])

    def reflection(self, slot):
        run_id = self.record()["runs"][slot]["run_id"]
        run = self.store.get("runs", run_id)
        failures = [
            e for e in self.store.list("evaluations", {"outcome": "failed"}) if not e.get("diagnostic")
        ]
        assert failures, "A known failed replay evaluation is required"
        context = {
            "evaluations": failures[:2],
            "specification": SPECIFICATION,
            "release": self.engine.improvements.active(),
            "diagnostic": "Explicit validation using archived real replay failures; not a live generation failure.",
        }
        provider = self.engine.provider(run)
        prior = self.record()["checks"].get("reflection", {})
        tool = self.store.get("tools", prior.get("tool_id", ""))
        if not tool or tool["status"] != "active":
            proposal = provider.tool(context)
            tool = self.engine.improvements.create_tool(
                proposal.source, proposal.summary, run_id, failures[0]["_id"]
            )
        self.save(
            "reflection", passed=False, tool_id=tool["_id"], tool_status=tool["status"], diagnostic=True
        )
        assert tool["status"] == "active"
        patch = provider.patch(context)
        release = self.engine.improvements.propose_release(patch, run_id, failures[0]["_id"])
        self.save(
            "reflection",
            passed=False,
            tool_id=tool["_id"],
            release_id=release["_id"],
            release_status=release["status"],
            diagnostic=True,
        )
        assert release["status"] == "validated"
        assert self.engine.improvements.activate(release["_id"], run_id)
        restarted = Engine(self.settings)
        result = restarted.improvements.invoke_tool(
            tool["_id"], {"dimensions_m": [2, 3, 4], "direction": [0, 0, 1]}, run_id
        )
        assert result["projected_area_m2"] == 6
        bad = restarted.improvements.propose_release(
            PatchProposal(
                summary="Explicit rejected-release diagnostic",
                files={"orchestrator.py": "raise RuntimeError('diagnostic')"},
            ),
            run_id,
            failures[0]["_id"],
        )
        assert bad["status"] == "rejected"
        assert restarted.improvements.active()["_id"] == release["_id"]
        self.save(
            "reflection",
            passed=True,
            tool_id=tool["_id"],
            release_id=release["_id"],
            rejected_release_id=bad["_id"],
            reused_after_restart=True,
            diagnostic=True,
        )

    def inspect(self, slot):
        from davinci.browser import inspect_candidate

        run_id = self.record()["runs"][slot]["run_id"]
        evaluations = self.store.list("evaluations", {"run_id": run_id, "outcome": "passed"})
        candidate = next(e["candidate_id"] for e in evaluations if e.get("artifacts", {}).get("model.glb"))
        existing = {i["_id"] for i in self.store.list("inspections", {"candidate_id": candidate})}
        inspect_candidate(self.settings, candidate)
        inspections = [
            i
            for i in self.store.list("inspections", {"candidate_id": candidate})
            if i["_id"] not in existing and i.get("geometry_artifact_id")
        ]
        assert inspections
        self.save(
            "inspection", passed=True, candidate_id=candidate, inspection_ids=[i["_id"] for i in inspections]
        )

    def reuse(self, slot):
        run_id = self.record()["runs"][slot]["run_id"]
        reflection = self.record()["checks"]["reflection"]
        assert reflection["passed"]
        candidates = self.store.list("candidates", {"run_id": run_id})
        assert len(candidates) >= 2
        assert all(c["release_id"] == reflection["release_id"] for c in candidates)
        assert all(reflection["tool_id"] in c["tool_version_ids"] for c in candidates)
        invocations = self.store.list("events", {"run_id": run_id, "kind": "tool_invoked"})
        assert any(e["data"]["tool_id"] == reflection["tool_id"] for e in invocations)
        assert self.store.list("champions", {"run_id": run_id})
        states = self.store.list("agent_states", {"run_id": run_id})
        assert all(s["retrieved_memory_ids"] for s in states)
        self.save(
            "promoted_release_reuse",
            passed=True,
            run_id=run_id,
            release_id=reflection["release_id"],
            tool_id=reflection["tool_id"],
            candidates=len(candidates),
            memory_retrieved=True,
        )

    def export(self, slot):
        import httpx

        run_id = self.record()["runs"][slot]["run_id"]
        headers = (
            {"authorization": "Bearer " + self.settings.davinci_api_token}
            if self.settings.davinci_api_token
            else {}
        )
        response = httpx.get(f"http://127.0.0.1:8215/api/runs/{run_id}/bundle", headers=headers, timeout=120)
        response.raise_for_status()
        path = self.root / f"{slot}.zip"
        path.write_bytes(response.content)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            assert "run.json" in names and "specification.json" in names
            manifest = json.loads(archive.read("artifact-manifest.json"))
            for item in manifest:
                content = archive.read(f"artifacts/{item['_id']}/{item['name']}")
                assert hashlib.sha256(content).hexdigest() == item["sha256"]
        # Verify all run evaluation artifacts independently through GridFS too.
        count = 0
        with tempfile.TemporaryDirectory(dir=self.root) as empty:
            remote = Artifacts(empty, self.store)
            for evaluation in self.store.list("evaluations", {"run_id": run_id}):
                for artifact in evaluation.get("artifacts", {}).values():
                    remote.read(artifact)
                    count += 1
        self.save(
            "export_" + slot,
            passed=True,
            archive=str(path),
            entries=len(names),
            manifest_hashes_verified=len(manifest),
            remote_artifacts_verified=count,
        )

    def report(self):
        record = self.record()
        ledger = self.store.get("budgets", "budget-global") or {}
        ids = {r["run_id"] for r in record["runs"].values()}
        spent = sum(v for k, v in ledger.get("runs", {}).items() if k in ids)
        held = sum(v["amount"] for v in ledger.get("reservations", {}).values() if v["run_id"] in ids)
        self.save("budget", passed=spent + held <= 25, spent_usd=spent, held_usd=held, limit_usd=25)
        emit(checks=self.record()["checks"], runs=record["runs"])

    def diagnose(self, slot):
        run_id = self.record()["runs"][slot]["run_id"]
        run = self.store.get("runs", run_id)
        emit(
            run_id=run_id,
            status=run["status"],
            error=run.get("error"),
            errors=[
                {"message": e["message"], "data": e["data"]}
                for e in self.store.list("events", {"run_id": run_id, "kind": "job_error"})
            ],
            candidates=[
                {"id": c["_id"], "subsystem": c["subsystem"], "release_id": c["release_id"]}
                for c in self.store.list("candidates", {"run_id": run_id})
            ],
        )
        probe = self.record()["checks"].get("triggers", {}).get("diagnostic_run_id")
        if probe:
            emit(
                trigger_probe_jobs=[
                    {"kind": j["kind"], "subject_id": j["subject_id"]}
                    for j in self.store.list("jobs", {"run_id": probe})
                ]
            )

    def acceptance(self):
        import httpx
        from playwright.sync_api import expect, sync_playwright

        self.report()
        record = self.record()
        reuse = record["checks"].get("promoted_release_reuse", {})
        slot = next(name for name, item in record["runs"].items() if item["run_id"] == reuse.get("run_id"))
        required = [
            "infrastructure",
            "recovery",
            "triggers",
            "replay",
            "live1",
            "vector",
            "reflection",
            "inspection",
            "promoted_release_reuse",
            "export_live1",
            "export_" + slot,
            "budget",
        ]
        assert all(record["checks"].get(name, {}).get("passed") for name in required)
        assert not self.store.list("runs", {"status": "running"})
        assert record["checks"]["budget"]["held_usd"] == 0
        headers = (
            {"authorization": "Bearer " + self.settings.davinci_api_token}
            if self.settings.davinci_api_token
            else {}
        )
        response = httpx.get("http://127.0.0.1:8215/api/health", headers=headers, timeout=30)
        response.raise_for_status()
        health = response.json()
        assert health["storage"] == "atlas" and health["cad_available"] and health["live_available"]
        assert self.settings.davinci_use_atlas_triggers
        screenshot = self.root / "final-workbench.png"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--enable-unsafe-swiftshader"])
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            errors = []
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            page.goto(self.settings.davinci_web_url, wait_until="domcontentloaded", timeout=60000)
            expect(page.locator(".viewport-label")).to_contain_text("EVALUATED CAD GEOMETRY", timeout=60000)
            page.locator('[data-testid="cad-canvas"][data-geometry-ready="true"]').wait_for(timeout=30000)
            page.screenshot(path=str(screenshot), full_page=True)
            assert not errors
            browser.close()
        self.save(
            "acceptance",
            passed=True,
            required_checks=required,
            active_runs=0,
            web_url=self.settings.davinci_web_url,
            storage="atlas",
            triggers_enabled=True,
            final_screenshot=str(screenshot),
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "stage",
        choices=[
            "prepare",
            "infrastructure",
            "recovery",
            "triggers",
            "run",
            "monitor",
            "vector",
            "reflection",
            "inspect",
            "reuse",
            "export",
            "report",
            "diagnose",
            "acceptance",
        ],
    )
    parser.add_argument("--slot", choices=["replay", *ALLOCATIONS], default="replay")
    parser.add_argument("--rounds", type=int, default=4)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    try:
        validation = Validation()
        if args.stage == "run":
            validation.run(args.slot, args.rounds)
        elif args.stage == "monitor":
            return 0 if validation.monitor(args.slot, args.seconds) else 1
        elif args.stage in ("vector", "reflection", "inspect", "reuse", "export", "diagnose"):
            getattr(validation, args.stage)(args.slot)
        else:
            result = getattr(validation, args.stage)()
            if result is False:
                return 1
    except Exception as exc:
        emit(stage=args.stage, passed=False, error_type=type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
