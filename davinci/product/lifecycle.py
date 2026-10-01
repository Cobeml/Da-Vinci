"""Validated lifecycle operations. No provider calls and no host execution of agent code.

The run document is the atomic aggregate: referenced blobs may be orphaned after
an interrupted write, but cannot become accepted evidence without its CAS commit.
"""

import json
import time
from copy import deepcopy

from jsonschema import validate

from davinci.models import digest, identity, now
from davinci.product.adapters import assess
from davinci.product.contracts import (
    Candidate,
    CapabilityReport,
    Command,
    Coverage,
    EvaluationResult,
    Evaluator,
    ExperienceReference,
    OpenExperiment,
    Plan,
    Runtime,
    SimulationJob,
    Verification,
)
from davinci.product.evidence import archive, manifest
from davinci.product.execution import build, evaluate_test, execution_failure, execution_identity, failure
from davinci.runner import SandboxError


class Conflict(ValueError):
    """Revision, ownership, operation identity, or state conflict (HTTP 409)."""


class Lifecycle:
    def __init__(self, engine):
        self.engine = engine
        self.store = engine.store
        self.artifacts = engine.artifacts

    def get(self, experiment_id):
        row = self.store.get("runs", experiment_id)
        if not row:
            raise KeyError(experiment_id)
        if row.get("lifecycle_version") != 2:
            from davinci.product.compatibility import legacy_view

            return legacy_view(row)
        return row

    def open(self, request):
        request = OpenExperiment.model_validate(request)
        key = (
            "experiment-"
            + digest(
                {**self.engine.experience.scope, "actor": request.actor, "operation": request.operation_id}
            )[:24]
        )
        historical_key = (
            "experiment-" + digest({"actor": request.actor, "operation": request.operation_id})[:24]
        )
        historical = self.store.get("runs", historical_key)
        if historical and not historical.get("workspace_id"):
            raise Conflict(
                "Historical unscoped opening operation exists; inspect its experiment ID and use a new operation ID for a scoped experiment"
            )
        prior = self.store.get("runs", key)
        payload = request.model_dump()
        if prior:
            if prior["opening"] != payload:
                raise Conflict("Opening operation was already used with different arguments")
            return prior
        if request.parent_experiment_id:
            self.get(request.parent_experiment_id)
        row = {
            "_id": key,
            "created_at": now(),
            "lifecycle_version": 2,
            **self.engine.experience.scope,
            "driver": request.driver,
            "mode": request.mode,
            "actor": request.actor,
            "object_id": request.object.slug,
            "description": request.description,
            "opening": payload,
            "phase": "draft",
            "status": "draft",
            "revision": 0,
            "pending_input": [],
            "plan": Plan().model_dump(),
            "evaluator": None,
            "runtime": None,
            "suite_id": None,
            "draft_only": False,
            "verifications": [],
            "fixtures": [],
            "candidates": [],
            "results": [],
            "experiences": [],
            "job": None,
            "history": [],
            "operations": {},
            "report": None,
            "parent_experiment_id": request.parent_experiment_id,
            "guarantees": "test-first-v2",
            "budget_usd": request.budget_usd,
            "spent_usd": 0,
            "provider_settings": self.engine.options.model_dump(),
        }
        if not self.store.insert("runs", row):
            return self.open(request)
        return row

    def _begin(self, eid, command, action, payload=None, phases=None):
        command = Command.model_validate(command)
        row = self.get(eid)
        if row.get("lifecycle_version") != 2:
            raise Conflict("Historical v1 runs use the compatibility driver")
        if row["actor"] != command.actor:
            raise Conflict("Operation belongs to a different driver owner")
        signature = digest({"action": action, "payload": payload, "actor": command.actor})
        receipt = row["operations"].get(command.operation_id)
        if receipt:
            if receipt["signature"] != signature:
                raise Conflict("Operation identifier reused with different arguments")
            return row, command, signature, True
        if row["revision"] != command.revision:
            raise Conflict("Revision conflict; reload before advancing")
        if phases and row["phase"] not in phases:
            raise Conflict(f"{action} is not allowed in {row['phase']}")
        if len(row["operations"]) >= 500:
            raise Conflict("Experiment operation limit reached; open a linked experiment")
        return row, command, signature, False

    def _commit(self, row, command, signature, action, fields):
        operations = {
            **row["operations"],
            command.operation_id: {
                "signature": signature,
                "action": action,
                **({"job_id": fields["job"]["id"]} if fields.get("job") else {}),
                "revision": row["revision"] + 1,
            },
        }
        fields = {
            **fields,
            "operations": operations,
            "revision": row["revision"] + 1,
            "history": [
                *row["history"],
                {
                    "action": action,
                    "actor": command.actor,
                    "operation_id": command.operation_id,
                    "at": now(),
                    "revision": row["revision"] + 1,
                    "phase": fields.get("phase", row["phase"]),
                },
            ],
        }
        if len(json.dumps({**row, **fields}, allow_nan=False).encode()) > 8_000_000:
            raise ValueError("Experiment ledger exceeds 8 MB; open a linked experiment")
        updated = self.store.update(
            "runs", row["_id"], fields, {"revision": row["revision"], "actor": command.actor}
        )
        if not updated:
            raise Conflict("Revision conflict; operation was not committed")
        return updated

    def update_plan(self, eid, command, plan, evaluator=None, runtime=None):
        plan = Plan.model_validate(plan)
        evaluator = Evaluator.model_validate(evaluator) if evaluator is not None else None
        runtime = Runtime.model_validate(runtime) if runtime is not None else None
        payload = {
            "plan": plan.model_dump(),
            "evaluator": evaluator.model_dump() if evaluator else None,
            "runtime": runtime.model_dump() if runtime else None,
            "execution_id": execution_identity()[0],
        }
        row, cmd, sig, done = self._begin(eid, command, "update_plan", payload, {"draft", "awaiting_input"})
        if done:
            return row
        pending = [r.description for r in plan.requirements if r.critical and not r.resolved]
        if not plan.requirements:
            pending.append("Define the engineering requirements")
        # Old verification evidence is retained but its identity will no longer match.
        artifact = self.artifacts.put(
            json.dumps(payload, sort_keys=True).encode(), "plan.json", "application/json"
        )
        return self._commit(
            row,
            cmd,
            sig,
            "update_plan",
            {
                **payload,
                "plan_id": digest(payload["plan"]),
                "evaluator_id": digest(payload["evaluator"]) if evaluator else None,
                "runtime_id": digest(payload["runtime"]) if runtime else None,
                "pending_input": pending,
                "phase": "awaiting_input" if pending else "draft",
                "plan_revisions": [*row.get("plan_revisions", []), artifact],
            },
        )

    def fixture(self, eid, command, *, step, provenance):
        """Import inspected CAD/reference geometry before freeze; never a candidate."""
        if not isinstance(step, bytes) or not step or len(step) > 32_000_000 or not provenance:
            raise ValueError("Reference STEP bytes (<=32 MB) and provenance required")
        payload = {"sha256": digest(step.hex()), "provenance": provenance}
        row, cmd, sig, done = self._begin(eid, command, "fixture", payload, {"draft", "awaiting_input"})
        if done:
            return row
        artifact = self.artifacts.put(step, "reference.step", "application/step")
        return self._commit(
            row,
            cmd,
            sig,
            "fixture",
            {
                "fixtures": [
                    *row["fixtures"],
                    {
                        "artifact": artifact,
                        "provenance": provenance,
                        "purpose": "reference_only",
                        "actor": cmd.actor,
                    },
                ],
            },
        )

    def _context(self, row):
        if not row.get("evaluator") or not row.get("runtime"):
            raise ValueError("Evaluator and pinned runtime are required")
        if row.get("execution_id") != execution_identity()[0]:
            raise Conflict("Harness implementation changed; open a linked revision and reverify")
        return (
            Plan.model_validate(row["plan"]),
            Evaluator.model_validate(row["evaluator"]),
            Runtime.model_validate(row["runtime"]),
        )

    def _execution_claim(self, row, cmd, sig, action, job):
        # Same slot as the managed v1 worker. A second process cannot claim it.
        with self.engine.lock:
            if self.engine.busy or not self.store.update(
                "pointers", "product-active-run", {"run_id": row["_id"]}, {"run_id": None}
            ):
                raise Conflict("Another execution is active")
            try:
                return self._commit(
                    row,
                    cmd,
                    sig,
                    action,
                    {
                        "job": job,
                        "phase": "verifying" if action == "verify" else "evaluating",
                        "resume_phase": row["phase"],
                        "status": "running",
                    },
                )
            except Exception:
                self.engine.release(row["_id"])
                raise

    def _finish(self, eid, job_id, fields):
        # Cancellation can change the revision while a solver is finishing.
        # The job token fences late results after restart/recovery.
        def finish(row):
            job = row.get("job")
            if not job or job["id"] != job_id or job["status"] != "running":
                raise Conflict("Execution owner no longer holds this job")
            cancelled = row["phase"] == "cancelled"
            finished = deepcopy(fields)
            if cancelled:
                if "verifications" in finished:
                    finished["verifications"][-1]["matched"] = False
                if "results" in finished:
                    result = finished["results"][-1]
                    result.update(
                        evidence_complete=False, design_accepted=False, objective_target_attained=None
                    )
                    result["tests"] = [
                        failure(t["id"], "not_run", "cancelled").model_dump() for t in row["plan"]["tests"]
                    ]
            if "results" in finished:
                finished["results"][-1]["job"]["status"] = "cancelled" if cancelled else "completed"
            if len(json.dumps({**row, **finished}, allow_nan=False).encode()) > 8_000_000:
                raise ValueError("Experiment ledger exceeds 8 MB; execution evidence cannot be committed")
            return {
                **finished,
                "phase": "cancelled" if cancelled else fields["phase"],
                "status": "cancelled" if cancelled else "active",
                "job": {**job, "status": "cancelled" if cancelled else "completed"},
                "jobs": {
                    **row.get("jobs", {}),
                    job_id: {**job, "status": "cancelled" if cancelled else "completed"},
                },
                "history": [
                    *row["history"],
                    {"action": "execution_finished", "job_id": job_id, "actor": "harness", "at": now()},
                ],
            }

        updated = self.store.mutate("runs", eid, finish)
        if "results" in fields:
            try:
                self.engine.experience.observe(updated, updated["results"][-1])
            except Exception as exc:
                # The run remains the evidence source of truth. Explicit memory capture can retry indexing.
                self.store.event(
                    eid,
                    "memory_projection_pending",
                    "Evidence committed; experience indexing needs retry",
                    error_type=type(exc).__name__,
                )
        return updated

    def _cancel_check(self, eid):
        row = self.get(eid)
        return self.engine.shutdown.is_set() or row["phase"] in ("cancelled", "interrupted")

    def verify(self, eid, command, verification):
        verification = Verification.model_validate(verification)
        row, cmd, sig, done = self._begin(eid, command, "verify", verification.model_dump(), {"draft"})
        if done:
            return row
        plan, evaluator, runtime = self._context(row)
        test = next((t for t in plan.tests if t.id == verification.test_id), None)
        if not test or verification.fixture_artifact not in [f["artifact"] for f in row["fixtures"]]:
            raise ValueError("Verification requires a declared test and reference fixture")
        if set(verification.reference_metrics) != set(test.metrics):
            raise ValueError("Verification must cover every declared metric")
        if any(verification.reference_metrics[k].unit != unit for k, unit in test.metrics.items()):
            raise ValueError("Reference metric units differ from test")
        job_id = identity("verification")
        job = {"id": job_id, "owner": cmd.actor, "operation_id": cmd.operation_id, "status": "running"}
        row = self._execution_claim(row, cmd, sig, "verify", job)
        return self._run_verification(row, verification)

    def _run_verification(self, row, verification):
        eid, job = row["_id"], row["job"]
        plan, evaluator, runtime = self._context(row)
        test = next(t for t in plan.tests if t.id == verification.test_id)
        self.engine.runner.cancelled = lambda: self._cancel_check(eid)
        try:
            result, outputs, log, duration = evaluate_test(
                self.engine.runner,
                self.artifacts.read(verification.fixture_artifact),
                plan,
                test,
                evaluator,
                runtime,
            )
            matched = result.status == verification.expected_status and all(
                k in result.metrics
                and abs(result.metrics[k].value - value.value) <= verification.tolerances[k]
                for k, value in verification.reference_metrics.items()
            )
            refs = self._archive_outputs(outputs, log, runtime.artifact_bytes)
            evidence_manifest = manifest(
                self.artifacts,
                refs,
                {k: row[k] for k in ("plan_id", "evaluator_id", "runtime_id", "execution_id")},
            )
            record = {
                "id": job["id"],
                "plan_id": row["plan_id"],
                "evaluator_id": row["evaluator_id"],
                "runtime_id": row["runtime_id"],
                "execution_id": row["execution_id"],
                "request": verification.model_dump(),
                "result": result.model_dump(),
                "matched": matched and evidence_manifest.complete and not self._cancel_check(eid),
                "evidence": refs,
                "manifest": evidence_manifest.model_dump(),
                "duration_seconds": duration,
                "actor": job["owner"],
                "at": now(),
            }
            return self._finish(
                eid, job["id"], {"phase": "draft", "verifications": [*row["verifications"], record]}
            )
        finally:
            self.engine.runner.cancelled = lambda: False
            self.engine.release(eid)

    def capabilities(self, eid):
        row = self.get(eid)
        plan = Plan.model_validate(row["plan"])
        reports = []
        for test in plan.tests:
            checks = [
                v
                for v in row["verifications"]
                if v["request"]["test_id"] == test.id
                and all(
                    v.get(k) == row.get(k) for k in ("plan_id", "evaluator_id", "runtime_id", "execution_id")
                )
            ]
            good = [v for v in checks if v["matched"]]
            kinds = {v["request"]["expected_status"] for v in good}
            status = "verified" if kinds == {"pass", "physical_failure"} else "unverified"
            if any(not check["matched"] for check in checks):
                status = "unverified"
            if checks and checks[-1]["result"]["status"] == "unsupported_capability":
                status = "unavailable"
            assessment = (
                assess(self.engine.runner, plan, test, Runtime.model_validate(row["runtime"]))
                if row.get("runtime")
                else {}
            )
            if assessment.get("issues"):
                status = "unavailable"
            reports.append(
                CapabilityReport(
                    runtime_id=row.get("runtime_id") or "unconfigured",
                    test_id=test.id,
                    status=status,
                    reason="; ".join(i["needed"] for i in assessment.get("issues", []))
                    if assessment.get("issues")
                    else (
                        "Positive and negative reference checks matched"
                        if status == "verified"
                        else "Missing or failed positive/negative reference checks"
                    ),
                    verification_ids=[v["id"] for v in good],
                    simulation=assessment,
                ).model_dump()
            )
        return reports

    def freeze(self, eid, command, *, draft_only=False):
        row, cmd, sig, done = self._begin(eid, command, "freeze", {"draft_only": draft_only}, {"draft"})
        if done:
            return row
        plan, evaluator, runtime = self._context(row)
        if row["pending_input"] or not plan.requirements or not plan.tests:
            raise ValueError("Requirements and tests must be defined before freezing")
        critical = {r.id for r in plan.requirements if r.critical}
        covered = {r for t in plan.tests if t.required for r in t.requirements}
        if not critical <= covered:
            raise ValueError("Required test coverage is missing for critical requirements")
        coverage = Coverage(
            requirement_tests={
                r.id: [t.id for t in plan.tests if r.id in t.requirements] for r in plan.requirements
            },
            uncovered_critical=sorted(critical - covered),
            complete=critical <= covered,
        )
        reports = self.capabilities(eid)
        gaps = [r["test_id"] for r in reports if r["status"] != "verified"]
        if gaps and not draft_only:
            raise ValueError("Test verification incomplete; explicitly freeze draft_only or verify all tests")
        if gaps and draft_only and any(r["status"] != "unavailable" for r in reports if r["test_id"] in gaps):
            raise ValueError(
                "Draft freeze requires recorded unavailable capability evidence, not skipped verification"
            )
        suite = {
            "plan_id": row["plan_id"],
            "evaluator_id": row["evaluator_id"],
            "runtime_id": row["runtime_id"],
            "execution_id": row["execution_id"],
            "draft_only": bool(draft_only),
            "capabilities": reports,
        }
        artifact = self.artifacts.put(
            json.dumps(suite, sort_keys=True).encode(), "suite.json", "application/json"
        )
        harness_artifact = self.artifacts.put(
            json.dumps(execution_identity()[1]).encode(), "execution-sources.json", "application/json"
        )
        return self._commit(
            row,
            cmd,
            sig,
            "freeze",
            {
                "suite_id": digest(suite),
                "suite_artifact": artifact,
                "execution_artifact": harness_artifact,
                "phase": "frozen",
                "status": "active",
                "draft_only": bool(draft_only),
                "coverage": coverage.model_dump(),
                "capabilities": reports,
                "validation_gaps": gaps,
                "frozen_at": now(),
            },
        )

    def submit_candidate(self, eid, command, candidate):
        candidate = Candidate.model_validate(candidate)
        row, cmd, sig, done = self._begin(
            eid, command, "submit_candidate", candidate.model_dump(), {"frozen", "reflected"}
        )
        if done:
            return row
        if not row["suite_id"]:
            raise Conflict("A frozen plan must precede candidate submission")
        validate(candidate.parameters, row["plan"]["design_schema"])
        cid = identity("candidate")
        source = self.artifacts.put(candidate.source.encode(), "build.py", "text/x-python")
        commit = self.engine.repository.commit(
            cid,
            {
                "build.py": candidate.source,
                "parameters.json": json.dumps(candidate.parameters),
                "suite.txt": row["suite_id"],
            },
        )
        record = {
            "id": cid,
            "iteration": len(row["candidates"]),
            "title": candidate.title,
            "change": candidate.change,
            "parameters": candidate.parameters,
            "source_artifact": source,
            "source_commit": commit,
            "candidate_version": digest(candidate.model_dump()),
            "metadata": candidate.metadata,
            "suite_id": row["suite_id"],
            "actor": cmd.actor,
            "operation_id": cmd.operation_id,
            "at": now(),
        }
        return self._commit(
            row,
            cmd,
            sig,
            "submit_candidate",
            {
                "phase": "candidate_submitted",
                "candidates": [*row["candidates"], record],
            },
        )

    def _archive_outputs(self, outputs, log, limit=256_000_000):
        return archive(self.artifacts, outputs, log, limit=limit)

    def request_evaluation(self, eid, command):
        row, cmd, sig, done = self._begin(eid, command, "evaluate", None, {"candidate_submitted"})
        if done:
            return row
        plan, evaluator, runtime = self._context(row)
        candidate = row["candidates"][-1]
        job = SimulationJob(
            id=identity("simulation"),
            candidate_id=candidate["id"],
            suite_id=row["suite_id"],
            runtime_id=row["runtime_id"],
            owner=cmd.actor,
            status="running",
            operation_id=cmd.operation_id,
        ).model_dump()
        row = self._execution_claim(row, cmd, sig, "evaluate", job)
        return self._run_evaluation(row)

    def _run_evaluation(self, row):
        eid, job = row["_id"], row["job"]
        plan, evaluator, runtime = self._context(row)
        candidate = row["candidates"][-1]
        self.engine.runner.cancelled = lambda: self._cancel_check(eid)
        try:
            proposal = Candidate(
                title=candidate["title"],
                parameters=candidate["parameters"],
                source=self.artifacts.read(candidate["source_artifact"]).decode(),
            )
            results, artifacts, duration = [], {}, 0
            started = time.monotonic()
            build_outputs = {}
            try:
                step, log, duration = build(
                    self.engine.runner, proposal, plan, runtime, evidence=build_outputs
                )
                # Builder outputs other than CAD/resources remain untrusted and do not enter evidence.
                trusted = {k: v for k, v in build_outputs.items() if k in ("model.step", "resources.json")}
                trusted["timing.json"] = json.dumps({"duration_seconds": duration}).encode()
                artifacts = self._archive_outputs(trusted, log, runtime.artifact_bytes)
            except (SandboxError, OSError) as exc:
                results = [execution_failure(t.id, exc, building=True) for t in plan.tests]
                artifacts = self._archive_outputs(
                    getattr(exc, "outputs", {}), getattr(exc, "log", ""), runtime.artifact_bytes
                )
                duration = getattr(exc, "duration", 0)
            if not results:
                for test in plan.tests:
                    spent = sum(self.store.get("artifacts", a)["size"] for a in artifacts.values())
                    remaining = min(runtime.job_seconds, runtime.compute_seconds / runtime.cpu_cores) - max(
                        duration, time.monotonic() - started
                    )
                    if spent >= runtime.artifact_bytes or remaining < 1:
                        results.append(
                            failure(
                                test.id,
                                "not_run",
                                "resource_exhaustion",
                                "Cumulative job time/compute/artifact budget exhausted",
                            )
                        )
                        continue
                    bounded = runtime.model_copy(
                        update={
                            "job_seconds": remaining,
                            "compute_seconds": remaining * runtime.cpu_cores,
                            "artifact_bytes": runtime.artifact_bytes - spent,
                        }
                    )
                    if bounded.artifact_bytes < 1024:
                        results.append(failure(test.id, "not_run", "artifact_quota"))
                        continue
                    result, outputs, log, seconds = evaluate_test(
                        self.engine.runner, step, plan, test, evaluator, bounded
                    )
                    results.append(result)
                    artifacts.update(
                        {
                            test.id + "/" + k: v
                            for k, v in self._archive_outputs(outputs, log, bounded.artifact_bytes).items()
                        }
                    )
                    duration += seconds
            if self._cancel_check(eid):
                results = [failure(t.id, "not_run", "cancelled") for t in plan.tests]
            record = {
                "id": identity("result"),
                "candidate_id": candidate["id"],
                "job": {
                    k: job[k]
                    for k in (
                        "id",
                        "candidate_id",
                        "suite_id",
                        "runtime_id",
                        "owner",
                        "status",
                        "operation_id",
                    )
                },
                "suite_id": row["suite_id"],
                "plan_id": row["plan_id"],
                "evaluator_id": row["evaluator_id"],
                "runtime_id": row["runtime_id"],
                "source_artifact": candidate["source_artifact"],
                "candidate_version": candidate["candidate_version"],
                "execution_id": row["execution_id"],
                "tests": [r.model_dump() for r in results],
                "artifacts": artifacts,
                "duration_seconds": duration,
                "at": now(),
                "actor": "harness",
            }
            record["manifest"] = manifest(
                self.artifacts,
                artifacts,
                {
                    "job_id": job["id"],
                    **{
                        k: record[k]
                        for k in (
                            "suite_id",
                            "plan_id",
                            "evaluator_id",
                            "runtime_id",
                            "execution_id",
                            "candidate_version",
                            "source_artifact",
                        )
                    },
                },
            ).model_dump()
            record.update(self._decision(row, record))
            record = EvaluationResult.model_validate(record).model_dump()
            return self._finish(eid, job["id"], {"phase": "evaluated", "results": [*row["results"], record]})
        finally:
            self.engine.runner.cancelled = lambda: False
            self.engine.release(eid)

    def _decision(self, row, record):
        plan = Plan.model_validate(row["plan"])
        results = {r["test_id"]: r for r in record["tests"]}
        required = [t for t in plan.tests if t.required]

        def prescribed(test):
            if test.id not in results or results[test.id]["status"] not in ("pass", "physical_failure"):
                return False
            spec = test.simulation
            if spec:
                metadata = results[test.id].get("metadata", {})
                if any(metadata.get(k) != getattr(spec, k) for k in ("adapter", "fidelity", "stage")):
                    return False
            return True

        final_coverage = {
            r for t in required if not t.simulation or t.simulation.stage == "final" for r in t.requirements
        }
        critical = {r.id for r in plan.requirements if r.critical}
        complete = (
            bool(required)
            and critical <= final_coverage
            and all(prescribed(t) for t in required)
            and record.get("manifest", {}).get("complete", False)
        )
        accepted = (
            complete and not row["draft_only"] and all(results[t.id]["status"] == "pass" for t in required)
        )
        attained = None
        objective = plan.objective
        if objective and objective.target is not None:
            values = [
                r["metrics"][objective.metric]["value"]
                for r in results.values()
                if r["status"] in ("pass", "physical_failure") and objective.metric in r["metrics"]
            ]
            if values:
                attained = all(
                    v <= objective.target if objective.direction == "minimize" else v >= objective.target
                    for v in values
                )
        return {
            "execution_completed": True,
            "evidence_complete": complete,
            "design_accepted": accepted,
            "objective_target_attained": attained,
        }

    def reflect(self, eid, command, *, lesson, result_id=None):
        row, cmd, sig, done = self._begin(
            eid, command, "reflect", {"lesson": lesson, "result_id": result_id}, {"evaluated"}
        )
        if done:
            return row
        candidate = row["candidates"][-1]
        if result_id and not any(
            r["id"] == result_id and r["candidate_id"] == candidate["id"] for r in row["results"]
        ):
            raise ValueError("Reflection evidence must belong to the current candidate")
        experience = ExperienceReference(
            experiment_id=eid,
            candidate_id=candidate["id"],
            result_id=result_id,
            lesson=lesson,
            support="linked_observation" if result_id and row["driver"] == "managed" else "hypothesis",
        ).model_dump()
        updated = self._commit(
            row, cmd, sig, "reflect", {"phase": "reflected", "experiences": [*row["experiences"], experience]}
        )
        try:
            self.engine.experience.note(
                {
                    "actor": cmd.actor,
                    "operation_id": "reflection-" + digest({"eid": eid, "operation": cmd.operation_id}),
                    "experiment_id": eid,
                    "claim": lesson,
                    "source": {"run_id": eid, "candidate_id": candidate["id"], "result_id": result_id},
                }
            )
        except Exception as exc:
            self.store.event(
                eid,
                "memory_projection_pending",
                "Reflection preserved; experience note needs indexing",
                error_type=type(exc).__name__,
            )
        return updated

    def retrieve(self, query, *, experiment_id=None, limit=8):
        return self.engine.experience.search(
            {"query": query, "experiment_id": experiment_id, "limit": max(1, min(limit, 30))}
        )["items"]

    def finalize(self, eid, command):
        row, cmd, sig, done = self._begin(eid, command, "finalize", None, {"reflected"})
        if done:
            return row
        self._context(row)
        # Recompute final checks, never trust a previously serialized acceptance flag.
        references = [row["suite_artifact"], row["execution_artifact"], *row["plan_revisions"]]
        references.extend(f["artifact"] for f in row["fixtures"])
        references.extend(f["source_artifact"] for f in row["fixtures"] if f.get("source_artifact"))
        references.extend(a for f in row["fixtures"] for a in f.get("evidence", {}).values())
        references.extend(artifact for v in row["verifications"] for artifact in v["evidence"].values())
        for artifact in references:
            self.artifacts.verify(artifact)
        for candidate in row["candidates"]:
            self.artifacts.read(candidate["source_artifact"])
        for result in row["results"]:
            for artifact in result["artifacts"].values():
                self.artifacts.verify(artifact)
            if result.get("manifest"):
                regenerated = manifest(
                    self.artifacts, result["artifacts"], result["manifest"]["provenance"]
                ).model_dump()
                if regenerated != result["manifest"]:
                    raise ValueError("Simulation artifact manifest mismatch")
        decisions = [
            {"result_id": r["id"], "candidate_id": r["candidate_id"], **self._decision(row, r)}
            for r in row["results"]
        ]
        report = {
            "version": 2,
            "suite_id": row["suite_id"],
            "completed_at": now(),
            "draft_only": row["draft_only"],
            "decisions": decisions,
            "accepted_candidate_ids": [d["candidate_id"] for d in decisions if d["design_accepted"]],
            "validation_gaps": row["validation_gaps"],
            "guarantees": row["guarantees"],
        }
        artifact = self.artifacts.put(json.dumps(report).encode(), "report.json", "application/json")
        return self._commit(
            row,
            cmd,
            sig,
            "finalize",
            {"phase": "completed", "status": "completed", "report": report, "report_artifact": artifact},
        )

    def cancel(self, eid, command):
        row, cmd, sig, done = self._begin(eid, command, "cancel", None)
        if done:
            return row
        if row["phase"] in ("completed", "cancelled"):
            raise Conflict("Experiment is already terminal")
        return self._commit(
            row,
            cmd,
            sig,
            "cancel",
            {
                "phase": "cancelled",
                "status": "cancelled",
                **(
                    {
                        "job": {**row["job"], "status": "cancelled"},
                        "jobs": {
                            **row.get("jobs", {}),
                            row["job"]["id"]: {**row["job"], "status": "cancelled"},
                        },
                    }
                    if row.get("job") and row["job"]["status"] == "queued"
                    else {}
                ),
                "resume_phase": row.get("resume_phase")
                if row["phase"] in ("evaluating", "verifying", "queued")
                else row["phase"],
            },
        )

    def resume(self, eid, command):
        row, cmd, sig, done = self._begin(eid, command, "resume", None, {"interrupted", "cancelled"})
        if done:
            return row
        if row.get("job") and row["job"]["status"] == "running":
            raise Conflict("Wait for cancellation to finish before resuming")
        uncertain = self.store.list(
            "requests", {"run_id": eid, "status": {"$in": ["pending", "received", "uncertain"]}}
        )
        if uncertain:
            raise Conflict("An uncertain model request cannot be repeated; open a linked experiment")
        phase = row.get("resume_phase") or "draft"
        if row["results"] and row["results"][-1]["candidate_id"] == (
            row["candidates"][-1]["id"] if row["candidates"] else None
        ):
            phase = "evaluated"
        return self._commit(row, cmd, sig, "resume", {"phase": phase, "status": "active"})

    def recover(self):
        # Called only at exclusive server startup, as with the v1 worker.
        for row in self.store.list("runs", {"lifecycle_version": 2}, limit=10000):
            if row.get("job") and row["job"]["status"] == "running":
                cancelled = row["phase"] == "cancelled"
                self.store.update(
                    "runs",
                    row["_id"],
                    {
                        "phase": "cancelled" if cancelled else "interrupted",
                        "status": "cancelled" if cancelled else "paused",
                        "revision": row["revision"] + 1,
                        "jobs": {
                            **row.get("jobs", {}),
                            row["job"]["id"]: {
                                **row["job"],
                                "status": "cancelled" if cancelled else "interrupted",
                                "reason": "cancelled" if cancelled else "interrupted",
                            },
                        },
                        "job": {
                            **row["job"],
                            "status": "cancelled" if cancelled else "interrupted",
                            "reason": "cancelled" if cancelled else "interrupted",
                        },
                    },
                    {"revision": row["revision"]},
                )

    def revise(self, eid, request):
        """Evaluator corrections always open linked drafts; no evidence is copied."""
        old = self.get(eid)
        request = OpenExperiment.model_validate(request)
        if request.parent_experiment_id != eid:
            raise ValueError("Revision must link its parent experiment")
        new = self.open(request)
        if new["revision"] == 0 and old.get("lifecycle_version") == 2:
            return self.update_plan(
                new["_id"],
                Command(actor=request.actor, revision=0, operation_id="inherit-plan"),
                deepcopy(old["plan"]),
                old["evaluator"],
                old["runtime"],
            )
        return new

    def validate_plan(self, eid):
        """Read-only readiness report; shares freeze's validation path without committing."""
        row = self.get(eid)
        plan = Plan.model_validate(row["plan"])
        covered = {r for t in plan.tests if t.required for r in t.requirements}
        issues = [
            f"Uncovered requirement: {r.id}" for r in plan.requirements if r.critical and r.id not in covered
        ]
        issues.extend(row["pending_input"])
        if not plan.requirements or not plan.tests:
            issues.append("Define requirements and tests")
        try:
            self._context(row)
        except (ValueError, Conflict) as exc:
            issues.append(str(exc))
        capabilities = self.capabilities(eid)
        gaps = [r for r in capabilities if r["status"] != "verified"]
        return {
            "version": 2,
            "experiment_id": eid,
            "revision": row["revision"],
            "issues": issues,
            "capabilities": capabilities,
            "ready_to_freeze": not issues and not gaps,
            "ready_for_draft": not issues and all(r["status"] == "unavailable" for r in gaps),
        }

    def schedule(self, eid, command, kind, payload=None):
        """Persist explicit physical work for the single workspace worker. Never infer a proposal."""
        phases = {"evaluate": {"candidate_submitted"}, "verify": {"draft"}, "reference_build": {"draft"}}
        if kind not in phases:
            raise ValueError("Unknown simulation operation")
        if kind == "verify":
            payload = Verification.model_validate(payload).model_dump()
        elif kind == "reference_build":
            from davinci.product.contracts import ReferenceBuild

            payload = ReferenceBuild.model_validate(payload).model_dump()
        elif payload is not None:
            raise ValueError("Evaluation accepts no caller-supplied results or inputs")
        row, cmd, sig, done = self._begin(eid, command, kind, payload, phases[kind])
        if done:
            receipt = row["operations"][cmd.operation_id]
            return self.job(eid, receipt["job_id"])
        plan, _, _ = self._context(row)
        if kind == "verify":
            test = next((t for t in plan.tests if t.id == payload["test_id"]), None)
            if not test or payload["fixture_artifact"] not in [f["artifact"] for f in row["fixtures"]]:
                raise ValueError("Verification requires a declared test and reference fixture")
            if set(payload["reference_metrics"]) != set(test.metrics) or any(
                payload["reference_metrics"][k]["unit"] != u for k, u in test.metrics.items()
            ):
                raise ValueError("Verification must cover declared metrics in their exact units")
        if kind == "reference_build":
            validate(payload["candidate"]["parameters"], plan.design_schema)
        jid = identity("job")
        job = {
            "version": 2,
            "id": jid,
            "experiment_id": eid,
            "kind": kind,
            "owner": cmd.actor,
            "operation_id": cmd.operation_id,
            "status": "queued",
            "created_at": now(),
            "payload": payload,
            "suite_id": row.get("suite_id"),
            "runtime_id": row["runtime_id"],
            "plan_id": row["plan_id"],
            "evaluator_id": row["evaluator_id"],
            "execution_id": row["execution_id"],
            "candidate_id": row["candidates"][-1]["id"] if kind == "evaluate" else None,
        }
        # Commit the queue entry and receipt together; no cross-document handoff can be lost.
        updated = self._commit(
            row,
            cmd,
            sig,
            kind,
            {
                "phase": "queued",
                "status": "queued",
                "resume_phase": row["phase"],
                "job": job,
                "jobs": {**row.get("jobs", {}), jid: job},
            },
        )
        return self.job(eid, updated["job"]["id"])

    def job(self, eid, job_id):
        row = self.get(eid)
        job = (
            row.get("job") if (row.get("job") or {}).get("id") == job_id else row.get("jobs", {}).get(job_id)
        )
        if not job:
            raise KeyError(job_id)
        return {
            **{k: v for k, v in job.items() if k != "payload"},
            "next_actions": ["poll_job", "cancel"]
            if job["status"] in ("queued", "running")
            else ["inspect_results", "inspect_status"],
        }

    def execute_scheduled(self, eid):
        """Called only by Engine.work in the workspace service."""
        with self.engine.lock:
            row = self.get(eid)
            if row["phase"] != "queued" or row["job"]["status"] != "queued":
                return
            if self.engine.busy or not self.store.update(
                "pointers", "product-active-run", {"run_id": eid}, {"run_id": None}
            ):
                return
            job = {**row["job"], "status": "running", "started_at": now()}
            claimed = self.store.update(
                "runs",
                eid,
                {
                    "phase": "verifying" if job["kind"] == "verify" else "evaluating",
                    "status": "running",
                    "revision": row["revision"] + 1,
                    "job": job,
                    "jobs": {**row.get("jobs", {}), job["id"]: job},
                },
                {"revision": row["revision"], "phase": "queued"},
            )
            if not claimed:
                self.engine.release(eid)
                return
        try:
            if job["kind"] == "evaluate":
                self._run_evaluation(claimed)
            elif job["kind"] == "verify":
                self._run_verification(claimed, Verification.model_validate(job["payload"]))
            else:
                self._run_reference(claimed)
        except Exception as exc:
            # Unexpected host failure is not physical evidence. A new command is required after resume.
            current = self.get(eid)
            if current.get("job", {}).get("id") == job["id"] and current["job"]["status"] == "running":
                stopped = current["phase"] == "cancelled"
                failed = {
                    **current["job"],
                    "status": "cancelled" if stopped else "interrupted",
                    "reason": "cancelled" if stopped else "interrupted",
                    "error_type": type(exc).__name__,
                }
                self.store.update(
                    "runs",
                    eid,
                    {
                        "phase": "cancelled" if stopped else "interrupted",
                        "status": "cancelled" if stopped else "paused",
                        "job": failed,
                        "jobs": {**current.get("jobs", {}), job["id"]: failed},
                        "revision": current["revision"] + 1,
                    },
                    {"revision": current["revision"]},
                )
        finally:
            self.engine.runner.cancelled = lambda: False
            self.engine.release(eid)

    def _run_reference(self, row):
        eid, job = row["_id"], row["job"]
        plan, _, runtime = self._context(row)
        proposal = Candidate.model_validate(job["payload"]["candidate"])
        self.engine.runner.cancelled = lambda: self._cancel_check(eid)
        source = self.artifacts.put(proposal.source.encode(), "reference-build.py", "text/x-python")
        commit = self.engine.repository.commit(
            job["id"],
            {
                "build.py": proposal.source,
                "parameters.json": json.dumps(proposal.parameters),
                "purpose.txt": "reference_only",
            },
        )
        try:
            build_outputs = {}
            step, log, duration = build(self.engine.runner, proposal, plan, runtime, evidence=build_outputs)
            if self._cancel_check(eid):
                raise SandboxError("Reference build cancelled", reason="cancelled")
            artifact = self.artifacts.put(step, "reference.step", "application/step")
            evidence = self._archive_outputs(
                {k: v for k, v in build_outputs.items() if k in ("model.step", "resources.json")},
                log,
                runtime.artifact_bytes,
            )
            record = {
                "artifact": artifact,
                "provenance": job["payload"]["provenance"],
                "purpose": "reference_only",
                "actor": job["owner"],
                "job_id": job["id"],
                "source_artifact": source,
                "source_commit": commit,
                "parameters": proposal.parameters,
                "evidence": evidence,
                "manifest": manifest(
                    self.artifacts,
                    evidence,
                    {
                        "runtime_id": row["runtime_id"],
                        "execution_id": row["execution_id"],
                        "source_artifact": source,
                        "purpose": "reference_only",
                    },
                ).model_dump(),
                "duration_seconds": duration,
                "plan_id": row["plan_id"],
                "runtime_id": row["runtime_id"],
                "execution_id": row["execution_id"],
            }
            return self._finish(eid, job["id"], {"phase": "draft", "fixtures": [*row["fixtures"], record]})
        except (SandboxError, OSError) as exc:
            result = execution_failure("reference_build", exc, building=True).model_dump()
            return self._finish(
                eid,
                job["id"],
                {
                    "phase": "draft",
                    "reference_failures": [
                        *row.get("reference_failures", []),
                        {
                            "job_id": job["id"],
                            "result": result,
                            "source_artifact": source,
                            "evidence": self._archive_outputs(
                                getattr(exc, "outputs", {}), getattr(exc, "log", ""), runtime.artifact_bytes
                            ),
                        },
                    ],
                },
            )

    def export_report(self, eid):
        row = self.get(eid)
        if row["phase"] != "completed" or not row["report"]:
            raise Conflict("Finalize the experiment before exporting its report")
        return {
            "version": 2,
            "experiment": row,
            "report": row["report"],
            "artifacts_base_url": "/api/v1/artifacts/",
            "contains_geometry_bytes": False,
        }
