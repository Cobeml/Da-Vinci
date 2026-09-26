import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget, BudgetExceeded
from davinci.errors import safe_error
from davinci.improvement import Improvements
from davinci.memory import Memory
from davinci.models import SPECIFICATION, digest, document, now
from davinci.providers import AstraProvider, ReplayProvider
from davinci.runner import Runner, SandboxError
from davinci.store import Store
from davinci.templates import MOUNT_SOURCE, WING_SOURCE


class Engine:
    def __init__(self, settings, store=None, runner=None):
        self.settings = settings
        trusted = Path(__file__).resolve().parent.parent / "sandbox"
        self.evaluator_version = (
            "screening-"
            + digest(
                {
                    "specification": SPECIFICATION,
                    "sources": {
                        name: (trusted / name).read_text()
                        for name in ("evaluate.py", "integrate.py", "families.py")
                    },
                }
            )[:12]
        )
        self.store = store or Store(settings.root, settings.mongodb_uri, settings.mongodb_database)
        self.artifacts = Artifacts(settings.root, self.store)
        self.repository = Repository(settings.root)
        self.runner = runner or Runner(settings)
        self.improvements = Improvements(self.store, self.artifacts, self.repository, self.runner)
        self.budget = Budget(self.store, settings.davinci_daily_budget_usd)
        self.store.insert("specifications", SPECIFICATION)
        self.improvements.initialize()
        self.store.insert("pointers", {"_id": "active-run", "run_id": None})

    def provider(self, run, subsystem=None):
        if run["mode"] == "replay":
            return ReplayProvider()

        def handler(name, args):
            if name == "invoke_tool":
                return self.improvements.invoke_tool(args["tool_version_id"], args["arguments"], run["_id"])
            if name == "search_memory":
                return self.memory(run).search(subsystem, args["query"], run_id=run["_id"])
            raise ValueError("Unknown tool")

        return AstraProvider(self.settings, self.budget, self.store, run["_id"], handler)

    def memory(self, run):
        provider = self.provider(run)
        return Memory(self.store, provider.embed if run["mode"] == "live" else None, self.evaluator_version)

    def start(self, request, run_id=None):
        # Internal validation callers can resume a named run after a crash.
        if run_id and (existing := self.store.get("runs", run_id)):
            return existing
        if request.mode == "live" and not self.settings.openai_api_key:
            raise ValueError("Set OPENAI_API_KEY before starting a live run")
        slot = self.store.get("pointers", "active-run")
        if slot["run_id"]:
            active = self.store.get("runs", slot["run_id"])
            if active and active["status"] == "running":
                raise ValueError("A run is already active; finish or stop it before starting another")
            self.store.update("pointers", "active-run", {"run_id": None}, {"run_id": slot["run_id"]})
        run = document(
            "run",
            project_id="uas-demo",
            mode=request.mode,
            status="running",
            phase="generating",
            round=0,
            max_rounds=request.rounds,
            budget_usd=min(request.budget_usd, self.settings.davinci_run_budget_usd),
            spent_usd=0.0,
            revision=0,
            no_improvement_rounds=0,
            best_objective=None,
            specification_id=SPECIFICATION["_id"],
            evaluator_version=self.evaluator_version,
            release_id=self.improvements.active()["_id"],
            assembly_revision_id=None,
        )
        if run_id:
            run["_id"] = run_id
        root = Path(__file__).resolve().parent.parent
        paths = [
            root / "uv.lock",
            root / "pyproject.toml",
            root / "package-lock.json",
            *sorted((root / "sandbox").glob("*.py")),
            root / "sandbox/Dockerfile",
            root / "sandbox/requirements.lock",
            root / "sandbox/ui/check.cjs",
            root / "sandbox/ui/package-lock.json",
        ]
        environment = {str(path.relative_to(root)): path.read_text() for path in paths}
        run["environment_bundle_artifact_id"] = self.artifacts.put(
            self.repository.bundle(environment), "environment.json", "application/json"
        )
        run["environment_source_commit"] = self.repository.commit(
            "environment-" + digest(environment)[:16], environment
        )
        self.store.insert("runs", run)
        if not self.store.update("pointers", "active-run", {"run_id": run["_id"]}, {"run_id": None}):
            self.store.update("runs", run["_id"], {"status": "rejected"})
            raise ValueError("A concurrent request already started a run")
        self.store.event(
            run["_id"],
            "run_started",
            f"{'Deterministic replay' if request.mode == 'replay' else 'Astra live'} run started",
        )
        self.store.enqueue("generate_round", f"{run['_id']}:0", run["_id"])
        return run

    def stop(self, id):
        run = self.store.update(
            "runs", id, {"status": "stopped", "finished_at": now()}, {"status": "running"}
        )
        if run:
            self.store.event(id, "run_stopped", "Run stopped; active containers are being cancelled")
            self.store.update("pointers", "active-run", {"run_id": None}, {"run_id": id})
        return run

    def generate(self, job):
        run = self.store.get("runs", job["run_id"])
        number = int(job["subject_id"].rsplit(":", 1)[1])
        if number != run["round"]:
            return
        release = self.store.get("releases", run["release_id"])

        def generate_one(subsystem):
            id = f"candidate-{run['_id']}-{number}-{subsystem}"
            if self.store.get("candidates", id):
                return
            memory = self.memory(run)
            retrieved = memory.search(
                subsystem, f"{subsystem} geometric failures thickness hinge clearance", run_id=run["_id"]
            )
            # Prefer the latest validated utility while retaining all versions
            # in the archive and making them available to the specialist.
            tools = self.store.list("tools", {"status": "active"}, reverse=True)
            context = {
                "specification": SPECIFICATION,
                "round": number,
                "release": release,
                "memory": retrieved,
                "reference_source": MOUNT_SOURCE if subsystem == "structural" else WING_SOURCE,
                "tools": [{k: t[k] for k in ("_id", "name", "summary", "input_schema")} for t in tools],
            }
            proposal = self.provider(run, subsystem).propose(subsystem, number, context)
            try:
                adapted = self.runner.adapt(
                    release["files"], [{"subsystem": subsystem, "parameters": proposal.parameters}]
                )[0]
            except Exception:
                # Cancellation is not a regression in the active harness.
                if self.store.get("runs", run["_id"])["status"] == "running" and self.store.owns(job):
                    self.improvements.rollback(
                        release["_id"], run["_id"], "Orchestration failed during a live canary"
                    )
                raise
            # Parameters are schema-constrained after executing editable orchestration.
            from davinci.models import Proposal

            proposal = Proposal.model_validate({**proposal.model_dump(), "parameters": adapted})
            fingerprint = digest(
                {
                    "source": proposal.source,
                    "parameters": adapted,
                    "spec": SPECIFICATION["_id"],
                    "evaluator": self.evaluator_version,
                }
            )
            repeated = memory.failed_before(fingerprint)
            state = document(
                "state",
                run_id=run["_id"],
                role=subsystem,
                model=self.provider(run).name,
                release_id=release["_id"],
                retrieved_memory_ids=[m["_id"] for m in retrieved],
                tool_version_ids=[t["_id"] for t in tools],
                decision_summary=proposal.summary,
            )
            self.store.insert("agent_states", state)
            files = {"candidate.py": proposal.source, "parameters.json": json.dumps(adapted, sort_keys=True)}
            commit = self.repository.commit(id, files)
            candidate = {
                **document("candidate"),
                "_id": id,
                "project_id": "uas-demo",
                "run_id": run["_id"],
                "round": number,
                "subsystem": subsystem,
                "parameters": adapted,
                "source": proposal.source,
                "summary": proposal.summary,
                "source_commit": commit,
                "source_bundle_artifact_id": self.artifacts.put(
                    self.repository.bundle(files), "source.json", "application/json"
                ),
                "specification_id": SPECIFICATION["_id"],
                "evaluator_version": self.evaluator_version,
                "fingerprint": fingerprint,
                "release_id": release["_id"],
                "agent_state_id": state["_id"],
                "assembly_revision_id": run["assembly_revision_id"],
                "tool_version_ids": [t["_id"] for t in tools],
                "repeated_failure": repeated,
            }
            if not self.store.owns(job):
                return
            self.store.insert("candidates", candidate)
            self.store.event(
                run["_id"],
                "candidate_committed",
                f"{subsystem.title()} candidate committed",
                candidate_id=id,
                round=number,
            )
            if tools:
                self.improvements.invoke_tool(
                    tools[0]["_id"],
                    {
                        "dimensions_m": [0.08, 0.04, adapted.get("thickness_mm", 3) / 1000],
                        "direction": [1, 0, 0],
                    },
                    run["_id"],
                )
            if not self.settings.davinci_use_atlas_triggers:
                self.store.enqueue("evaluate_candidate", id, run["_id"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(generate_one, ["structural", "aerodynamic"]))
        self.store.update(
            "runs",
            run["_id"],
            {"phase": "evaluating"},
            {"status": "running", "round": number, "phase": "generating"},
        )

    def evaluate(self, job):
        candidate = self.store.get("candidates", job["subject_id"])
        id = "evaluation-" + candidate["_id"]
        if self.store.get("evaluations", id):
            return
        started = time.monotonic()
        if candidate["repeated_failure"]:
            result = {
                "outcome": "failed",
                "metrics": {},
                "violations": [
                    {
                        "code": "REPEATED_FAILURE",
                        "message": "Exact failed source/parameter combination already evaluated",
                    }
                ],
                "objective": None,
                "fidelity": "analytic_screening",
            }
            outputs = {}
        else:
            try:
                result, outputs, _ = self.runner.evaluate(
                    candidate["source"], candidate["parameters"], candidate["subsystem"], SPECIFICATION
                )
            except SandboxError as exc:
                if not self.runner.available():
                    raise
                result = {
                    "outcome": "failed",
                    "metrics": {},
                    "violations": [{"code": "CAD_EXECUTION", "message": str(exc)[-2000:]}],
                    "objective": None,
                    "fidelity": "analytic_screening",
                }
                outputs = {"execution.log": str(exc).encode()}
        artifacts = {
            name: self.artifacts.put(
                data,
                name,
                {"model.step": "application/step", "model.glb": "model/gltf-binary"}.get(name, "text/plain"),
            )
            for name, data in outputs.items()
        }
        evaluation = {
            **document("evaluation"),
            "_id": id,
            "candidate_id": candidate["_id"],
            "run_id": candidate["run_id"],
            "round": candidate["round"],
            "subsystem": candidate["subsystem"],
            "evaluator_version": self.evaluator_version,
            "runtime_image_digest": self.runner.image_digest(),
            **result,
            "artifacts": artifacts,
            "duration_seconds": time.monotonic() - started,
        }
        if self.store.owns(job) and self.store.get("runs", job["run_id"])["status"] == "running":
            self.store.insert("evaluations", evaluation)
            self.store.event(
                job["run_id"],
                "evaluation_completed",
                f"{candidate['subsystem'].title()}: {result['outcome']}",
                evaluation_id=id,
                violations=result["violations"],
            )
            if not self.settings.davinci_use_atlas_triggers:
                self.store.enqueue("reflect_on_evaluation", id, job["run_id"])

    def reflect(self, job):
        evaluation = self.store.get("evaluations", job["subject_id"])
        candidate = self.store.get("candidates", evaluation["candidate_id"])
        run = self.store.get("runs", job["run_id"])
        self.memory(run).remember(candidate, evaluation)
        self.complete_round(run, job)

    def complete_round(self, run, job):
        number = run["round"]
        evaluations = self.store.list("evaluations", {"run_id": run["_id"], "round": number})
        if len(evaluations) != 2 or any(
            not self.store.get("memories", "memory-" + e["_id"]) for e in evaluations
        ):
            return
        claimed = self.store.update(
            "runs",
            run["_id"],
            {"phase": "reflecting", "reflection_job_id": job["_id"]},
            {"phase": {"$in": ["evaluating", "generating"]}, "status": "running", "round": number},
        )
        if not claimed and not (
            run.get("phase") == "reflecting" and run.get("reflection_job_id") == job["_id"]
        ):
            return
        failures = [e for e in evaluations if e["outcome"] != "passed"]
        pending_release = None
        if failures:
            provider = self.provider(run)
            context = {
                "evaluations": evaluations,
                "specification": SPECIFICATION,
                "release": self.improvements.active(),
            }
            if not self.store.list("tools", {"status": "active"}):
                proposal = provider.tool(context)
                self.improvements.create_tool(
                    proposal.source, proposal.summary, run["_id"], failures[0]["_id"]
                )
            patch = provider.patch(context)
            release = self.improvements.propose_release(patch, run["_id"], failures[0]["_id"])
            if release["status"] == "validated":
                pending_release = release["_id"]
        objective = None
        assembly = None
        if not failures:
            parts = {e["subsystem"]: self.artifacts.read(e["artifacts"]["model.step"]) for e in evaluations}
            integration, outputs = self.runner.integrate(
                parts["structural"], parts["aerodynamic"], SPECIFICATION
            )
            mass = integration["mass_kg"]
            feasible = integration["outcome"] == "passed"
            assembly = {
                **document("assembly"),
                "_id": f"assembly-{run['_id']}-{number}",
                "run_id": run["_id"],
                "round": number,
                "parent_id": run["assembly_revision_id"],
                "candidate_ids": [e["candidate_id"] for e in evaluations],
                "evaluation_ids": [e["_id"] for e in evaluations],
                "mass_kg": mass,
                "outcome": "passed" if feasible else "failed",
                "mount_translation_mm": SPECIFICATION["assembly"]["mount_translation_mm"],
                "violations": integration["violations"],
                "artifacts": {
                    name: self.artifacts.put(
                        content, name, "model/gltf-binary" if name.endswith("glb") else "application/step"
                    )
                    for name, content in outputs.items()
                },
            }
            assembly["interface_check"] = (
                "BRep collision and sampled control-surface travel against shared mount"
            )
            self.store.insert("assemblies", assembly)
            if feasible:
                aerodynamic = next(e for e in evaluations if e["subsystem"] == "aerodynamic")
                objective = (
                    mass / SPECIFICATION["baseline"]["assembly_mass_kg"] + aerodynamic["objective"]
                ) / 2
                champion = {
                    **document("champion"),
                    "_id": "champion-" + assembly["_id"],
                    "project_id": "uas-demo",
                    "run_id": run["_id"],
                    "specification_id": SPECIFICATION["_id"],
                    "evaluator_version": self.evaluator_version,
                    "assembly_id": assembly["_id"],
                    "candidate_ids": assembly["candidate_ids"],
                    "evaluation_ids": assembly["evaluation_ids"],
                    "release_id": run["release_id"],
                    "objective": objective,
                    "mass_kg": mass,
                    "induced_drag_n": next(e for e in evaluations if e["subsystem"] == "aerodynamic")[
                        "metrics"
                    ]["induced_drag_n"]["value"],
                }
                self.store.insert("champions", champion)
                self.store.event(
                    run["_id"],
                    "assembly_accepted",
                    "Shared assembly passed screening",
                    assembly_id=assembly["_id"],
                    objective=objective,
                )
        if not self.store.owns(job) or self.store.get("runs", run["_id"])["status"] != "running":
            return
        if pending_release:
            self.improvements.activate(pending_release, run["_id"])
        improved = objective is not None and (
            run["best_objective"] is None or objective < run["best_objective"] - 1e-8
        )
        stale = 0 if improved else run["no_improvement_rounds"] + 1
        done = number + 1 >= run["max_rounds"] or stale >= 3
        fields = {
            "round": number + 1,
            "phase": "completed" if done else "generating",
            "status": "completed" if done else "running",
            "release_id": self.improvements.active()["_id"],
            "no_improvement_rounds": stale,
            "best_objective": objective if improved else run["best_objective"],
            "assembly_revision_id": assembly["_id"]
            if assembly and assembly["outcome"] == "passed"
            else run["assembly_revision_id"],
        }
        if done:
            fields["finished_at"] = now()
        self.store.update(
            "runs",
            run["_id"],
            fields,
            {"status": "running", "round": number, "reflection_job_id": job["_id"]},
        )
        self.store.event(
            run["_id"], "run_completed" if done else "round_completed", f"Round {number + 1} completed"
        )
        if not done:
            self.store.enqueue("generate_round", f"{run['_id']}:{number + 1}", run["_id"])

    def reconcile(self):
        for run in self.store.list("runs", {"status": "running"}):
            if run["phase"] == "generating":
                self.store.enqueue("generate_round", f"{run['_id']}:{run['round']}", run["_id"])
            for candidate in self.store.list("candidates", {"run_id": run["_id"]}):
                if not self.store.get("evaluations", "evaluation-" + candidate["_id"]):
                    self.store.enqueue("evaluate_candidate", candidate["_id"], run["_id"])
            for evaluation in self.store.list("evaluations", {"run_id": run["_id"]}):
                self.store.enqueue("reflect_on_evaluation", evaluation["_id"], run["_id"])

    def execute_job(self, job):
        self.runner.cancelled = lambda: (
            self.store.get("runs", job["run_id"])["status"] != "running" or not self.store.owns(job)
        )
        try:
            {
                "generate_round": self.generate,
                "evaluate_candidate": self.evaluate,
                "reflect_on_evaluation": self.reflect,
            }[job["kind"]](job)
            self.store.finish(job)
        except BudgetExceeded as exc:
            self.store.update("runs", job["run_id"], {"status": "budget_exhausted", "error": str(exc)})
            self.store.finish(job)
        except Exception as exc:
            if self.store.get("runs", job["run_id"])["status"] == "stopped":
                self.store.update(
                    "jobs", job["_id"], {"status": "cancelled"}, {"lease_token": job["lease_token"]}
                )
                return
            result = self.store.finish(job, error=exc)
            self.store.event(
                job["run_id"], "job_error", safe_error(exc), job_id=job["_id"], attempt=job["attempt"]
            )
            if result and result["status"] == "dead":
                self.store.update("runs", job["run_id"], {"status": "failed", "error": safe_error(exc)})
        finally:
            self.runner.cancelled = lambda: False
