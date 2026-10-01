"""Validated lifecycle operations. No provider calls and no host execution of agent code.

The run document is the atomic aggregate: referenced blobs may be orphaned after
an interrupted write, but cannot become accepted evidence without its CAS commit.
"""

import json
import re
from copy import deepcopy

from jsonschema import validate

from davinci.models import digest, identity, now
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
        key = "experiment-" + digest({"actor": request.actor, "operation": request.operation_id})[:24]
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
                "history": [
                    *row["history"],
                    {"action": "execution_finished", "job_id": job_id, "actor": "harness", "at": now()},
                ],
            }

        return self.store.mutate("runs", eid, finish)

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
            record = {
                "id": job_id,
                "plan_id": row["plan_id"],
                "evaluator_id": row["evaluator_id"],
                "runtime_id": row["runtime_id"],
                "execution_id": row["execution_id"],
                "request": verification.model_dump(),
                "result": result.model_dump(),
                "matched": matched and not self._cancel_check(eid),
                "evidence": self._archive_outputs(outputs, log),
                "duration_seconds": duration,
                "actor": cmd.actor,
                "at": now(),
            }
            return self._finish(
                eid, job_id, {"phase": "draft", "verifications": [*row["verifications"], record]}
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
            reports.append(
                CapabilityReport(
                    runtime_id=row.get("runtime_id") or "unconfigured",
                    test_id=test.id,
                    status=status,
                    reason="Positive and negative reference checks matched"
                    if status == "verified"
                    else "Missing or failed positive/negative reference checks",
                    verification_ids=[v["id"] for v in good],
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

    def _archive_outputs(self, outputs, log):
        # Artifacts are provenance only; only validated result.json supplies measurements.
        return {
            name: self.artifacts.put(data, name, "application/octet-stream")
            for name, data in {**outputs, "execution.log": log.encode()}.items()
        }

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
        self.engine.runner.cancelled = lambda: self._cancel_check(eid)
        try:
            proposal = Candidate(
                title=candidate["title"],
                parameters=candidate["parameters"],
                source=self.artifacts.read(candidate["source_artifact"]).decode(),
            )
            results, artifacts, duration = [], {}, 0
            try:
                step, log, duration = build(self.engine.runner, proposal, plan, runtime)
                artifacts = self._archive_outputs({"model.step": step}, log)
            except (SandboxError, OSError) as exc:
                results = [execution_failure(t.id, exc, building=True) for t in plan.tests]
            if not results:
                for test in plan.tests:
                    result, outputs, log, seconds = evaluate_test(
                        self.engine.runner, step, plan, test, evaluator, runtime
                    )
                    results.append(result)
                    artifacts.update(
                        {test.id + "/" + k: v for k, v in self._archive_outputs(outputs, log).items()}
                    )
                    duration += seconds
            if self._cancel_check(eid):
                results = [failure(t.id, "not_run", "cancelled") for t in plan.tests]
            record = {
                "id": identity("result"),
                "candidate_id": candidate["id"],
                "job": job,
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
        complete = bool(required) and all(
            t.id in results and results[t.id]["status"] in ("pass", "physical_failure") for t in required
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
            support="linked_observation" if result_id else "hypothesis",
        ).model_dump()
        return self._commit(
            row, cmd, sig, "reflect", {"phase": "reflected", "experiences": [*row["experiences"], experience]}
        )

    def retrieve(self, query, *, experiment_id=None, limit=8):
        # No provider or embeddings needed, including when storage is Atlas.
        tokens = set(re.findall(r"\w+", query.lower()))
        hits = []
        for row in self.store.list("runs", {"lifecycle_version": 2}, limit=10000):
            for experience in row["experiences"]:
                hits.append(
                    {
                        **experience,
                        "suite_id": row["suite_id"],
                        "cross_task": row["_id"] != experiment_id,
                        "relevance": len(tokens & set(re.findall(r"\w+", experience["lesson"].lower()))),
                    }
                )
        for policy in self.store.list("policies", limit=10000):
            if not all(policy.get(k) for k in ("run_id", "candidate_id", "lesson")):
                continue
            experience = ExperienceReference(
                experiment_id=policy["run_id"],
                candidate_id=policy["candidate_id"],
                lesson=policy["lesson"][:4000],
            ).model_dump()
            hits.append(
                {
                    **experience,
                    "suite_id": None,
                    "cross_task": True,
                    "guarantees": "legacy-unverified-coverage",
                    "relevance": len(tokens & set(re.findall(r"\w+", experience["lesson"].lower()))),
                }
            )
        return sorted(hits, key=lambda r: r["relevance"], reverse=True)[: max(1, min(limit, 30))]

    def finalize(self, eid, command):
        row, cmd, sig, done = self._begin(eid, command, "finalize", None, {"reflected"})
        if done:
            return row
        self._context(row)
        # Recompute final checks, never trust a previously serialized acceptance flag.
        references = [row["suite_artifact"], row["execution_artifact"], *row["plan_revisions"]]
        references.extend(f["artifact"] for f in row["fixtures"])
        references.extend(artifact for v in row["verifications"] for artifact in v["evidence"].values())
        for artifact in references:
            self.artifacts.read(artifact)
        for candidate in row["candidates"]:
            self.artifacts.read(candidate["source_artifact"])
        for result in row["results"]:
            for artifact in result["artifacts"].values():
                self.artifacts.read(artifact)
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
                "resume_phase": row.get("resume_phase")
                if row["phase"] in ("evaluating", "verifying")
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
