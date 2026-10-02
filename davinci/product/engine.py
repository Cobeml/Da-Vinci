import ast
import json
import subprocess
import threading
from importlib.resources import files
from pathlib import Path

from davinci.artifacts import Artifacts, Repository
from davinci.budget import Budget, BudgetExceeded
from davinci.config import Settings
from davinci.errors import safe_error
from davinci.models import digest, document, now
from davinci.product.compatibility import LegacyAdapter, identities
from davinci.product.config import RunConfig, parse_yaml, workspace_settings
from davinci.product.experience import ExperienceMemory
from davinci.product.lifecycle import Conflict, Lifecycle
from davinci.product.managed import ManagedDriver
from davinci.product.provider import Provider, UncertainRequest
from davinci.product.tasks import RESOURCES, check_parameters, evaluate, snapshot
from davinci.runner import Runner, SandboxError
from davinci.store import Store


class Engine:
    def __init__(self, workspace, *, store=None, runner=None, provider=Provider, credentials=None):
        self.workspace = Path(workspace).resolve()
        self.root = self.workspace / ".davinci"
        self.root.mkdir(parents=True, exist_ok=True)
        self.options = workspace_settings(self.workspace)
        # Credential values are consumed internally only, never serialized or returned.
        self.credentials = credentials or Settings(_env_file=self.workspace / ".env")
        if self.options.storage == "atlas" and not self.credentials.mongodb_uri:
            raise ValueError("MONGODB_URI is required for Atlas storage")
        self.store = store or Store(
            self.root,
            self.credentials.mongodb_uri if self.options.storage == "atlas" else "",
            self.options.database,
        )
        self.artifacts = Artifacts(self.root, self.store)
        self.repository = Repository(self.root)
        self.runner = runner or Runner(Settings(_env_file=None, davinci_data_dir=self.root))
        self.provider_type = provider
        self.lock = threading.RLock()
        self.shutdown = threading.Event()
        self.busy = False
        self.store.insert("pointers", {"_id": "product-active-run", "run_id": None})
        self.experience = ExperienceMemory(self)
        self.lifecycle = Lifecycle(self)
        self.legacy = LegacyAdapter(self)
        self.managed = ManagedDriver(self)
        from davinci.product.tool_learning import ToolLearning

        self.tool_learning = ToolLearning(self)
        from davinci.product.measurements import Measurements

        self.measurements = Measurements(self)

    def validate(self, content):
        config = parse_yaml(content)
        task = snapshot(config, self.workspace)
        return config, task

    def start(self, content):
        config, task = self.validate(content)
        if config.run.mode == "live":
            if not self.credentials.openai_api_key:
                raise ValueError("Set OPENAI_API_KEY before a live run")
            if self.options.model != self.options.pricing_model:
                raise ValueError("Model and pricing_model must match")
        try:
            image = subprocess.check_output(
                ["docker", "image", "inspect", "--format={{.Id}}", task["image"]],
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            raise ValueError(
                "CAD image unavailable. Run davinci setup --template " + config.task.template
            ) from None
        return self.create_run(config, task, content, image)

    def create_run(self, config, task, content, image):
        """Called after preflight; kept separate to exercise lifecycle without Docker."""
        task = {
            **task,
            "source_version": task["version"],
            "version": digest({"source_version": task["version"], "runtime_image_digest": image}),
        }
        seed, parent = None, None
        if config.continuation:
            seed = self.store.get("candidates", config.continuation.seed_candidate_id)
            if (
                not seed
                or seed["object_id"] != config.object.slug
                or not seed.get("artifacts", {}).get("model.step")
            ):
                raise ValueError("Continuation needs a buildable candidate from this object")
            parent = self.store.get("runs", seed["run_id"])
            check_parameters(task, seed["parameters"])
        existing = self.store.get("objects", config.object.slug)
        if existing and existing["template"] != config.task.template:
            raise ValueError("Use a new object slug when changing template")
        run = document(
            "run",
            object_id=config.object.slug,
            lifecycle_version=1,
            **self.experience.scope,
            driver="managed",
            mode=config.run.mode,
            acceptance_identity=identities(task, config, image),
            config=config.model_dump(),
            original_yaml=content,
            task_version=task["version"],
            task=task,
            runtime_image_digest=image,
            parent_run_id=parent["_id"] if parent else None,
            seed_candidate_id=seed["_id"] if seed else None,
            status="running",
            phase="baseline",
            completed_iterations=0,
            spent_usd=0,
            revision=0,
            budget_usd=config.run.budget_usd,
            model=self.options.model,
            provider_settings=self.options.model_dump(),
            seed_parameters=seed["parameters"] if seed else task["baseline"],
            seed_source=seed["source"]
            if seed and parent["task_version"] == task["version"]
            else task["source"],
        )
        # A CAS in the shared store also serializes Atlas clients.
        with self.lock:
            if self.busy or not self.store.update(
                "pointers", "product-active-run", {"run_id": run["_id"]}, {"run_id": None}
            ):
                raise ValueError("Another run is active. Stop it or wait before starting.")
            try:
                self.store.insert(
                    "objects",
                    {
                        "_id": config.object.slug,
                        "created_at": now(),
                        "name": config.object.name,
                        "template": config.task.template,
                    },
                )
                if existing and existing["name"] != config.object.name:
                    self.store.update("objects", config.object.slug, {"name": config.object.name})
                self.store.insert("runs", run)
                self.store.event(run["_id"], "run_started", "Run started", object_id=run["object_id"])
            except Exception:
                self.release(run["_id"])
                raise
        return run

    def release(self, run_id):
        self.store.update("pointers", "product-active-run", {"run_id": None}, {"run_id": run_id})

    def ensure_running(self, run_id):
        row = self.store.get("runs", run_id)
        if self.shutdown.is_set() or row["status"] != "running":
            raise InterruptedError("Run paused or stopped")

    def stop(self, run_id):
        if (self.store.get("runs", run_id) or {}).get("lifecycle_version") == 2:
            raise ValueError("Use the v2 lifecycle cancel operation")
        with self.lock:
            run = self.store.update(
                "runs", run_id, {"status": "stopped", "phase": "stopped"}, {"status": "running"}
            )
            if not run:
                raise ValueError("Run is not active")
            if not self.busy:
                self.release(run_id)
            self.store.event(run_id, "run_stopped", "Run stopped; completed evidence retained")
            return run

    def resume(self, run_id):
        with self.lock:
            run = self.store.get("runs", run_id)
            if run and run.get("lifecycle_version") == 2:
                raise ValueError("Use the v2 lifecycle resume operation")
            if not run or run["status"] not in ("paused", "stopped"):
                raise ValueError("Only paused or stopped runs can resume")
            uncertain = self.store.list(
                "requests", {"run_id": run_id, "status": {"$in": ["pending", "uncertain", "received"]}}
            )
            if uncertain:
                raise ValueError(
                    "An API request has uncertain or invalid output. Continue from an existing iteration in a new run instead."
                )
            if self.busy or not self.store.update(
                "pointers", "product-active-run", {"run_id": run_id}, {"run_id": None}
            ):
                raise ValueError("Another run is active")
            self.store.update("runs", run_id, {"status": "running", "phase": "resuming", "error": None})
            self.store.event(run_id, "run_resumed", "Run resumed from saved checkpoints")
            return self.store.get("runs", run_id)

    def recover(self):
        self.lifecycle.recover()
        self.tool_learning.recover()
        for run in self.store.list("runs", {"status": "running"}, limit=10000):
            if run.get("lifecycle_version") == 2:
                continue
            self.store.update("runs", run["_id"], {"status": "paused", "phase": "interrupted"})
        self.store.update("pointers", "product-active-run", {"run_id": None})
        # Requests interrupted before settlement retain their conservative reservation as spend.
        budget = Budget(self.store, self.options.daily_budget_usd)
        for request in self.store.list("requests", {"status": {"$in": ["pending", "received"]}}, limit=10000):
            if request.get("reservation"):
                budget.settle(request["reservation"], request.get("cost_usd", request["reserved_usd"]))
            self.store.update("requests", request["_id"], {"status": "uncertain"})

    def work(self):
        while not self.shutdown.wait(0.3):
            with self.lock:
                pointer = self.store.get("pointers", "product-active-run")
                if not pointer["run_id"]:
                    queued = self.store.list("runs", {"lifecycle_version": 2, "phase": "queued"}, limit=1)
                    queued_id = queued[0]["_id"] if queued else None
                else:
                    queued_id = None
            if queued_id:
                self.lifecycle.execute_scheduled(queued_id)
                continue
            if not self.store.get("pointers", "product-active-run")["run_id"]:
                tool_jobs = self.store.list(
                    "tool_developments_v1", {**self.experience.scope, "phase": "queued"}, limit=1
                )
                if tool_jobs:
                    self.tool_learning.execute_scheduled(tool_jobs[0]["_id"])
                    continue
            if not self.store.get("pointers", "product-active-run")["run_id"]:
                automatic = self.store.list(
                    "runs",
                    {
                        "lifecycle_version": 2,
                        "driver": "managed",
                        "managed.status": "ready",
                        **self.experience.scope,
                        "phase": {
                            "$in": [
                                "draft",
                                "frozen",
                                "candidate_submitted",
                                "evaluated",
                                "reflected",
                                "completed",
                            ]
                        },
                    },
                    limit=1,
                )
                if automatic:
                    eid = automatic[0]["_id"]
                    try:
                        self.managed.workflow.tick(eid)
                    except Conflict:
                        continue  # A concurrent ownership/revision change fences this stage.
                    except Exception as exc:
                        self.store.event(eid, "managed_stage_interrupted", safe_error(exc))
                        current = self.lifecycle.get(eid)
                        if current["phase"] not in ("cancelled", "interrupted"):
                            self.store.update(
                                "runs",
                                eid,
                                {
                                    "phase": "interrupted",
                                    "resume_phase": current["phase"],
                                    "revision": current["revision"] + 1,
                                },
                                {"revision": current["revision"]},
                            )
                    continue
            with self.lock:
                pointer = self.store.get("pointers", "product-active-run")
                if not pointer["run_id"]:
                    continue
                run_id = pointer["run_id"]
                active = self.store.get("runs", run_id)
                if self.store.get("tool_developments_v1", run_id):
                    continue
                if active and active.get("lifecycle_version") == 2:
                    continue  # lifecycle work owns the shared slot; never enter the model loop
                self.busy = True
            try:
                self.execute(run_id)
            except (InterruptedError, SandboxError) as exc:
                if self.store.get("runs", run_id)["status"] == "running":
                    self.store.update("runs", run_id, {"status": "paused", "error": safe_error(exc)})
            except BudgetExceeded:
                self.store.update(
                    "runs",
                    run_id,
                    {
                        "status": "budget_exhausted",
                        "phase": "budget_exhausted",
                        "error": "Budget cannot cover the next request",
                    },
                )
            except Exception as exc:
                self.store.update(
                    "runs",
                    run_id,
                    {
                        "status": "paused" if isinstance(exc, UncertainRequest) else "failed",
                        "error": safe_error(exc),
                    },
                )
                self.store.event(run_id, "run_error", safe_error(exc))
            finally:
                with self.lock:
                    self.busy = False
                    self.release(run_id)
                self.runner.cancelled = lambda: False

    def memory(self, run, provider=None):
        """Cross-object lessons, never exact-score reuse; generation provider is not consulted."""
        if any(run.get(k) != v for k, v in self.experience.scope.items()):
            return []  # Unscoped historical memory requires explicit provenance-aware import.
        return self.experience.search(
            {"query": run["config"]["task"]["description"], "experiment_id": run["_id"], "limit": 8}
        )["items"]

    def execute(self, run_id):
        run = self.store.get("runs", run_id)
        if run.get("lifecycle_version") == 2:
            raise ValueError("Use validated lifecycle operations for v2 experiments")
        config, task = RunConfig.model_validate(run["config"]), run["task"]
        provider = self.provider_type(self, run)
        self.runner.cancelled = lambda: (
            self.shutdown.is_set() or self.store.get("runs", run_id)["status"] != "running"
        )
        for index in range(config.run.iterations + 1):
            self.ensure_running(run_id)
            cid = f"{run_id}-{index:03d}"
            candidate = self.store.get("candidates", cid)
            if not candidate:
                self.store.update("runs", run_id, {"phase": "baseline" if index == 0 else "generating"})
                context = {
                    "task": {k: task[k] for k in ("name", "parameters_schema", "specification", "metrics")},
                    "config": run["config"],
                    "seed_parameters": run["seed_parameters"],
                    "seed_source": run["seed_source"],
                    "history": self.memory(run, provider),
                    "memory_policy": "Cross-object records require applicability review. Imported claims and authored lessons are unverified; never transfer a passing score or silently relax this task's tests.",
                    "recent": self.store.list("candidates", {"run_id": run_id}, limit=6, reverse=True),
                    "tool_results": self.store.list("tool_uses", {"run_id": run_id}, limit=6, reverse=True),
                    "tools": self.store.list(
                        "tools",
                        {
                            "object_id": run["object_id"],
                            "task_version": run["task_version"],
                            "status": "passed",
                        },
                        limit=3,
                    ),
                }
                proposal = (
                    {
                        "title": "Seed baseline" if run["parent_run_id"] else "Baseline",
                        "change": "Independent evaluation of the starting geometry.",
                        "parameters": run["seed_parameters"],
                        "source": run["seed_source"],
                    }
                    if index == 0
                    else provider.request(
                        f"proposal-{index}",
                        "Propose one CAD improvement. Return title (short string), change (short string), parameters (matching schema), source (complete Python build(parameters, interfaces)). Respect immutable interfaces. The independent evaluator rejects unsupported geometry. Use prior failures, lessons, tested tool outputs and objective. Do not alter the evaluator.",
                        context,
                    )
                )
                candidate = document(
                    "candidate",
                    _id=cid,
                    run_id=run_id,
                    object_id=run["object_id"],
                    task_version=run["task_version"],
                    iteration=index,
                    title=str(proposal["title"])[:100],
                    change=str(proposal["change"])[:2000],
                    parameters=proposal["parameters"],
                    source=proposal["source"],
                    artifacts={},
                )
                if not isinstance(candidate["source"], str) or len(candidate["source"]) > 40000:
                    raise ValueError("Invalid candidate source")
                self.legacy.submit(run, candidate)
            evaluation = self.store.get("evaluations", "evaluation-" + cid)
            if not evaluation:
                evaluation = self.legacy.evaluate(run, config, task, candidate, evaluate)
            self.ensure_running(run_id)
            if not self.store.get("policies", "policy-" + cid):
                reflection = provider.request(
                    f"reflect-{index}",
                    "Review the independent result. Return lesson and next_focus strings. Do not suggest relaxing checks.",
                    {
                        "parameters": candidate["parameters"],
                        "evaluation": evaluation,
                        "task": run["config"]["task"],
                        "objective": run["config"]["objective"],
                    },
                )
                policy = document(
                    "policy",
                    _id="policy-" + cid,
                    run_id=run_id,
                    object_id=run["object_id"],
                    candidate_id=cid,
                    task_version=run["task_version"],
                    lesson=str(reflection["lesson"])[:4000],
                    next_focus=str(reflection["next_focus"])[:4000],
                )
                self.legacy.reflect(policy)
            policy = self.store.get("policies", "policy-" + cid)
            summary = json.dumps(
                {
                    "parameters": candidate["parameters"],
                    "evaluation": evaluation,
                    "lesson": policy["lesson"],
                    "next_focus": policy["next_focus"],
                }
            )
            mid = "memory-" + cid
            if not self.store.get("memories", mid):
                self.store.insert(
                    "memories",
                    document(
                        "memory",
                        _id=mid,
                        run_id=run_id,
                        object_id=run["object_id"],
                        task_version=run["task_version"],
                        summary=summary,
                    ),
                )
            self.experience.legacy_observe(run, self.store.get("candidates", cid), evaluation, policy)
            if index == 0 and task.get("tool_contract"):
                self.make_tool(run, provider)
            self.use_tools(run, cid, evaluation)
            self.store.update("runs", run_id, {"completed_iterations": index})
            self.store.event(run_id, "iteration_completed", f"Iteration {index} completed", candidate_id=cid)
        self.ensure_running(run_id)
        self.store.update("runs", run_id, {"status": "completed", "phase": "completed", "finished_at": now()})
        self.store.event(run_id, "run_completed", "Run completed")

    def make_tool(self, run, provider):
        existing = self.store.list(
            "tools",
            {"object_id": run["object_id"], "task_version": run["task_version"], "status": "passed"},
            limit=1,
        )
        key = "tool-" + run["_id"]
        if existing or self.store.get("tools", key):
            return
        proposal = provider.request(
            "tool",
            run["task"]["tool_contract"] + " Return source and summary strings.",
            {"history": self.memory(run, provider)},
        )
        source = proposal["source"]
        checks = {}
        status = "failed"
        try:
            if not isinstance(source, str) or len(source) > 12000:
                raise ValueError("Tool source exceeds limit")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.ImportFrom,))
                    or isinstance(node, ast.Import)
                    and any(a.name != "math" for a in node.names)
                ):
                    raise ValueError("Only math imports allowed")
                if isinstance(node, ast.Name) and (
                    node.id.startswith("__")
                    or node.id
                    in (
                        "open",
                        "eval",
                        "exec",
                        "compile",
                        "getattr",
                        "setattr",
                        "globals",
                        "locals",
                        "__import__",
                    )
                ):
                    raise ValueError("Tool must be a pure numeric utility")
                if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                    raise ValueError("Private attributes are not allowed")
            test = run["task"].get("tool_test_source") or RESOURCES.joinpath("tool_check.py").read_text()
            outputs, _, _ = self.runner.execute(
                "/input/check.py",
                {"tool.py": source, "check.py": test},
                image=run["runtime_image_digest"],
                timeout=30,
            )
            checks = json.loads(outputs["result.json"])
            if checks.get("passed") is not True:
                raise ValueError("Tool checks failed")
            status = "passed"
        except (ValueError, SyntaxError, SandboxError, KeyError) as exc:
            checks = {"error": safe_error(exc)}
        commit = self.repository.commit(key, {"tool.py": source, "checks.json": json.dumps(checks)})
        self.store.insert(
            "tools",
            document(
                "tool",
                _id=key,
                run_id=run["_id"],
                object_id=run["object_id"],
                task_version=run["task_version"],
                source=source,
                summary=str(proposal.get("summary", ""))[:2000],
                status=status,
                checks=checks,
                source_commit=commit,
            ),
        )
        self.store.event(run["_id"], "tool_tested", "Generated utility " + status)

    def use_tools(self, run, cid, evaluation):
        key = "tool-use-" + cid
        if self.store.get("tool_uses", key):
            return
        rows = self.store.list(
            "tools",
            {"object_id": run["object_id"], "task_version": run["task_version"], "status": "passed"},
            limit=1,
        )
        base = self.store.get("evaluations", "evaluation-" + run["_id"] + "-000")
        metric = run["config"]["objective"]["metric"]
        if not rows or not base or metric not in base["metrics"] or metric not in evaluation["metrics"]:
            return
        args = {
            "baseline": base["metrics"][metric]["value"],
            "current": evaluation["metrics"][metric]["value"],
            "direction": run["config"]["objective"]["direction"],
        }
        try:
            outputs, _, _ = self.runner.execute(
                "/input/invoke.py",
                {
                    "invoke.py": files("sandbox").joinpath("invoke.py").read_text(),
                    "tool.py": rows[0]["source"],
                    "arguments.json": json.dumps(args),
                },
                image=run["runtime_image_digest"],
                timeout=30,
            )
            result = json.loads(outputs["result.json"])
        except (SandboxError, ValueError, KeyError) as exc:
            result = {"error": safe_error(exc)}
        self.store.insert(
            "tool_uses",
            document(
                "tool-use",
                _id=key,
                run_id=run["_id"],
                candidate_id=cid,
                tool_id=rows[0]["_id"],
                arguments=args,
                result=result,
            ),
        )

    def detail(self, object_id):
        obj = self.store.get("objects", object_id)
        if not obj:
            raise KeyError(object_id)
        runs = self.store.list(
            "runs", {"object_id": object_id, "lifecycle_version": {"$ne": 2}}, limit=10000, reverse=True
        )
        designs = []
        for c in self.store.list("candidates", {"object_id": object_id}, limit=10000):
            designs.append(
                {
                    **c,
                    "evaluation": self.store.get("evaluations", "evaluation-" + c["_id"]),
                    "reflection": self.store.get("policies", "policy-" + c["_id"]),
                    "tool_use": self.store.get("tool_uses", "tool-use-" + c["_id"]),
                }
            )
        # Each run ranks against its own baseline and constraints only.
        for run in runs:
            metric = run["config"]["objective"]["metric"]
            passed = [
                c
                for c in designs
                if c["run_id"] == run["_id"]
                and c["evaluation"]
                and c["evaluation"]["outcome"] == "passed"
                and metric in c["evaluation"]["metrics"]
            ]
            best = (
                (min if run["config"]["objective"]["direction"] == "minimize" else max)(
                    passed, key=lambda c: c["evaluation"]["metrics"][metric]["value"]
                )
                if passed
                else None
            )
            run["best_id"] = best["_id"] if best else None
            run.pop("task", None)
        return {**obj, "runs": runs, "designs": designs}
