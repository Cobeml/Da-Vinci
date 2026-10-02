"""Versioned tool development on the workspace's single execution worker.

Tool checks confer construction-helper evidence, never design acceptance.
"""

import json
from copy import deepcopy

from davinci.errors import safe_error
from davinci.models import digest, identity, now
from davinci.product.contracts import Command
from davinci.product.evidence import archive, manifest
from davinci.product.lifecycle import Conflict
from davinci.product.memory_contracts import Applicability, SourceReference
from davinci.product.tool_contracts import ToolNeed
from davinci.product.tool_execution import (
    check_source,
    descriptor,
    execute,
    implementation_identity,
    references,
    source_hash,
)
from davinci.runner import SandboxError

COLLECTION = "tool_developments_v1"
IDLE = {"draft", "defined", "proposed", "tested", "rejected", "completed", "interrupted", "cancelled"}


class ToolLearning:
    def __init__(self, engine):
        self.engine, self.store, self.artifacts = engine, engine.store, engine.artifacts

    def get(self, tid):
        row = self.store.get(COLLECTION, tid)
        if not row or any(row.get(k) != v for k, v in self.engine.experience.scope.items()):
            raise KeyError("Tool development not in this project")
        return row

    def catalog(self):
        rows = self.store.list(COLLECTION, self.engine.experience.scope, limit=1000)
        return [
            {
                k: r[k]
                for k in (
                    "_id",
                    "name",
                    "need",
                    "phase",
                    "contract",
                    "contract_id",
                    "active_version",
                    "revision",
                )
            }
            for r in rows
        ]

    def open(self, request):
        body = ToolNeed.model_validate(request)
        run = self.engine.experience._run(body.experiment_id)
        if run.get("lifecycle_version") != 2 or run["actor"] != body.actor:
            raise Conflict("Tool need must belong to the current experiment owner")
        key = (
            "tool-development-"
            + digest({**self.engine.experience.scope, "actor": body.actor, "operation": body.operation_id})[
                :24
            ]
        )
        row = dict(
            _id=key,
            **self.engine.experience.scope,
            **body.model_dump(),
            created_at=now(),
            driver=run["driver"],
            revision=0,
            phase="draft",
            contract=None,
            contract_id=None,
            versions=[],
            active_version=None,
            promotions=[],
            operations={},
            history=[],
            jobs=[],
            job=None,
            effort_reserved=0,
            max_compute_seconds=1800,
        )
        if not self.store.insert(COLLECTION, row):
            prior = self.get(key)
            if any(prior[k] != v for k, v in body.model_dump().items()):
                raise Conflict("Tool opening operation reused with different content")
            return prior
        return row

    def _begin(self, tid, body, action):
        row = self.get(tid)
        payload = body.model_dump(exclude={"revision"})
        signature = digest({"action": action, "payload": payload})
        receipt = row["operations"].get(body.operation_id)
        if receipt:
            if receipt["signature"] != signature:
                raise Conflict("Tool operation reused with different content")
            return row, signature, True
        if action == "invoke":
            run = self.engine.experience._run(body.experiment_id)
            if run["actor"] != body.actor:
                raise Conflict("Invocation belongs to a different experiment owner")
        elif action == "cancel" and row.get("job"):
            if body.actor not in (row["actor"], row["job"]["actor"]):
                raise Conflict("Only the job or development owner may cancel")
        elif row["actor"] != body.actor:
            raise Conflict("Tool development has a different owner")
        if row["revision"] != body.revision:
            raise Conflict("Tool revision conflict")
        if row["phase"] not in IDLE and action != "cancel":
            raise Conflict("Tool execution is already queued or running")
        if len(row["operations"]) >= 200:
            raise Conflict("Tool development operation limit reached; open a linked development")
        return row, signature, False

    def _commit(self, row, body, sig, action, fields):
        changed = {
            **fields,
            "revision": row["revision"] + 1,
            "operations": {**row["operations"], body.operation_id: {"signature": sig, "action": action}},
            "history": [
                *row["history"],
                dict(action=action, actor=body.actor, operation_id=body.operation_id, at=now()),
            ],
        }
        if len(json.dumps({**row, **changed}).encode()) > 6_000_000:
            raise ValueError("Tool ledger too large; open a new development")
        result = self.store.update(COLLECTION, row["_id"], changed, {"revision": row["revision"]})
        if not result:
            raise Conflict("Tool revision conflict")
        return result

    def define(self, tid, body):
        row, sig, done = self._begin(tid, body, "define")
        if done:
            return row
        if row["contract"]:
            raise Conflict("Tool contract/tests are immutable; open a new development for corrections")
        r = body.runtime
        if (
            r.backend != "docker"
            or r.accelerator != "none"
            or r.memory_gb > 4
            or r.cpu_cores > 2
            or r.job_seconds > 300
            or r.compute_seconds > 600
            or r.artifact_bytes > 64_000_000
        ):
            raise ValueError(
                "CAD helper requires local CPU sandbox, <=4 GB, <=2 CPUs, <=300s/job, <=600 compute seconds, <=64MB artifacts"
            )
        contract = {
            **descriptor(),
            "runtime": r.model_dump(),
            "applicability": body.applicability,
            "promotion_policy": body.promotion_policy,
            "implementation_id": implementation_identity(),
        }
        return self._commit(
            row, body, sig, "define", dict(contract=contract, contract_id=digest(contract), phase="defined")
        )

    def propose(self, tid, body):
        row, sig, done = self._begin(tid, body, "propose")
        if done:
            return row
        if not row["contract"]:
            raise Conflict("Define the contract and independent checks before source")
        if len(row["versions"]) >= 20:
            raise Conflict("Tool version limit reached")
        if body.parent_version and not any(v["id"] == body.parent_version for v in row["versions"]):
            raise ValueError("Unknown parent version")
        bundle = {
            "source": body.source,
            "contract_id": row["contract_id"],
            "runtime": row["contract"]["runtime"],
            "implementation_id": row["contract"]["implementation_id"],
            "parent_version": body.parent_version,
        }
        version = {
            **bundle,
            "id": "tool-version-" + digest(bundle),
            "source_sha256": source_hash(body.source),
            "dependency_hash": digest(
                {"runtime": bundle["runtime"], "software": descriptor()["required_software"]}
            ),
            "summary": body.summary,
            "status": "proposed",
            "withdrawn": False,
            "actor": body.actor,
            "created_at": now(),
        }
        if any(v["id"] == version["id"] for v in row["versions"]):
            raise Conflict("Identical version already exists; reuse it")
        # Archive invalid/misleading proposals too; policy rejection is recorded by checks.
        version["source_artifact"] = self.artifacts.put(body.source.encode(), "helper.py", "text/x-python")
        version["contract_artifact"] = self.artifacts.put(
            json.dumps(row["contract"]).encode(), "tool-contract.json", "application/json"
        )
        version["source_commit"] = self.engine.repository.commit(
            version["id"], {"helper.py": body.source, "contract.json": json.dumps(row["contract"], indent=2)}
        )
        return self._commit(
            row, body, sig, "propose", dict(versions=[*row["versions"], version], phase="proposed")
        )

    def version(self, row, vid):
        result = next((v for v in row["versions"] if v["id"] == vid), None)
        if not result:
            raise KeyError("Unknown tool version")
        return result

    def compatible(self, row, version, *, tested=True):
        if (
            version["contract_id"] != row["contract_id"]
            or version["implementation_id"] != implementation_identity()
        ):
            raise Conflict("Tool contract or trusted checking runtime changed; re-develop/retest before use")
        if version["runtime"] != row["contract"]["runtime"] or version["dependency_hash"] != digest(
            {"runtime": version["runtime"], "software": descriptor()["required_software"]}
        ):
            raise Conflict("Pinned tool dependency/runtime identity mismatch")
        if digest(json.loads(self.artifacts.read(version["contract_artifact"]))) != row["contract_id"]:
            raise Conflict("Tool contract provenance corrupted")
        if source_hash(self.artifacts.read(version["source_artifact"]).decode()) != version["source_sha256"]:
            raise Conflict("Tool source provenance corrupted")
        if source_hash(version["source"]) != version["source_sha256"]:
            raise Conflict("Tool source hash mismatch")
        if tested and (version["status"] != "tested" or version["withdrawn"]):
            raise Conflict("Tool version is untested, rejected or withdrawn")
        if tested:
            for ref in version["evidence"]["manifest"]["entries"]:
                self.artifacts.verify(ref["artifact_id"])

    def _queue(self, row, body, sig, kind, version, **extra):
        reserve = min(
            version["runtime"]["compute_seconds"],
            version["runtime"]["job_seconds"] * version["runtime"]["cpu_cores"],
        )
        if row["effort_reserved"] + reserve > row["max_compute_seconds"]:
            raise Conflict("Tool development compute budget exhausted; no automatic retry/refund")
        job = dict(
            id=identity("tool-job"),
            kind=kind,
            version_id=version["id"],
            actor=body.actor,
            operation_id=body.operation_id,
            status="queued",
            reserved_compute_seconds=reserve,
            **extra,
        )
        return self._commit(
            row,
            body,
            sig,
            kind,
            dict(job=job, phase="queued", effort_reserved=row["effort_reserved"] + reserve),
        )

    def check(self, tid, body):
        row, sig, done = self._begin(tid, body, "check")
        if done:
            return row
        version = self.version(row, body.version_id)
        self.compatible(row, version, tested=False)
        if version["status"] in ("tested", "rejected"):
            raise Conflict(
                "Check evidence is immutable; propose a linked version to correct the implementation"
            )
        return self._queue(row, body, sig, "check", version)

    def promote(self, tid, body, *, rollback=False):
        action = "rollback" if rollback else "promote"
        row, sig, done = self._begin(tid, body, action)
        if done:
            return row
        version = self.version(row, body.version_id)
        versions, stack = deepcopy(row["versions"]), list(row["promotions"])
        if rollback:
            if len(stack) < 2 or row["active_version"] != body.version_id:
                raise Conflict("Rollback needs the current version and an earlier tested promotion")
            stack.pop()
            target = self.version(row, stack[-1])
            self.compatible(row, target)
            next(v for v in versions if v["id"] == body.version_id)["withdrawn"] = True
            active = target["id"]
        else:
            self.compatible(row, version)
            if row["active_version"] == version["id"]:
                raise Conflict("Version is already active")
            stack.append(version["id"])
            active = version["id"]
        updated = self._commit(
            row,
            body,
            sig,
            action,
            dict(
                active_version=active,
                promotions=stack,
                versions=versions,
                policy_decisions=[
                    *row.get("policy_decisions", []),
                    dict(action=action, version_id=body.version_id, reason=body.reason, at=now()),
                ],
            ),
        )
        self._remember(
            updated,
            version,
            {
                "id": "tool-policy-" + digest({"tid": tid, "op": body.operation_id}),
                "passed": not rollback,
                "reason": action,
                "artifacts": version["evidence"]["artifacts"],
            },
        )
        return updated

    def pin(self, eid, body):
        self.engine.experience._run(eid)
        life = self.engine.lifecycle
        payload = body.model_dump(exclude=set(Command.model_fields))
        command = Command.model_validate(body.model_dump(include=set(Command.model_fields)))
        row, cmd, sig, done = life._begin(
            eid, command, "pin_tool", payload, {"frozen", "evaluated", "reflected"}
        )
        if done:
            return row
        dev = self.get(body.development_id)
        version = self.version(dev, body.version_id)
        self.compatible(dev, version)
        if body.contract_id != dev["contract_id"] or dev["active_version"] != version["id"]:
            raise Conflict("Pin requires compatible contract and explicitly promoted version")
        pins = row.get("tool_pins", {})
        if dev["_id"] in pins:
            raise Conflict("Run tool pins are immutable; continue/open a new experiment to change versions")
        return life._commit(
            row,
            cmd,
            sig,
            "pin_tool",
            {
                "tool_pins": {
                    **pins,
                    dev["_id"]: {
                        "version_id": version["id"],
                        "contract_id": dev["contract_id"],
                        "runtime": version["runtime"],
                        "source_sha256": version["source_sha256"],
                        "dependency_hash": version["dependency_hash"],
                        "suite_id": row["suite_id"],
                    },
                }
            },
        )

    def invoke(self, tid, body):
        row, sig, done = self._begin(tid, body, "invoke")
        if done:
            return row
        run = self.engine.experience._run(body.experiment_id)
        if not run.get("suite_id") or run["phase"] not in ("frozen", "evaluated", "reflected"):
            raise Conflict("Design-helper invocation requires a frozen idle experiment")
        pin = run.get("tool_pins", {}).get(tid)
        if not pin:
            raise Conflict("Pin the tested tool before use")
        version = self.version(row, pin["version_id"])
        self.compatible(row, version)
        return self._queue(
            row,
            body,
            sig,
            "invoke",
            version,
            experiment_id=run["_id"],
            suite_id=run["suite_id"],
            arguments=body.arguments.model_dump(mode="json"),
            ownership_epoch=run.get("ownership_epoch", 0),
        )

    def cancel(self, tid, body):
        row, sig, done = self._begin(tid, body, "cancel")
        if done:
            return row
        if row["phase"] not in ("queued", "running"):
            raise Conflict("No active tool job")
        return self._commit(
            row, body, sig, "cancel", dict(phase="cancelled", job={**row["job"], "status": "cancelled"})
        )

    def recover(self):
        for row in self.store.list(
            COLLECTION, {**self.engine.experience.scope, "phase": {"$in": ["queued", "running"]}}, limit=1000
        ):
            self.store.update(
                COLLECTION,
                row["_id"],
                dict(
                    phase="interrupted",
                    revision=row["revision"] + 1,
                    job={**row["job"], "status": "interrupted"},
                    jobs=[*row["jobs"], {**row["job"], "status": "interrupted"}],
                ),
                {"revision": row["revision"]},
            )

    def execute_scheduled(self, tid):
        with self.engine.lock:
            row = self.get(tid)
            if (
                row["phase"] != "queued"
                or self.engine.busy
                or not self.store.update("pointers", "product-active-run", {"run_id": tid}, {"run_id": None})
            ):
                return
            row = self.store.update(
                COLLECTION,
                tid,
                dict(phase="running", job={**row["job"], "status": "running"}, revision=row["revision"] + 1),
                {"revision": row["revision"], "phase": "queued"},
            )
            if not row:
                self.engine.release(tid)
                return
            self.engine.busy = True
        job = row["job"]
        version = self.version(row, job["version_id"])

        def cancelled():
            current = self.get(tid)
            return (
                self.engine.shutdown.is_set()
                or current["job"]["id"] != job["id"]
                or current["job"]["status"] != "running"
            )

        self.engine.runner.cancelled = cancelled
        outputs, log, checks, reason = {}, "", [], "checks_failed"
        try:
            self.compatible(row, version, tested=job["kind"] == "invoke")
            if job["kind"] == "invoke":
                run = self.engine.experience._run(job["experiment_id"])
                if (
                    run["actor"] != job["actor"]
                    or run.get("ownership_epoch", 0) != job["ownership_epoch"]
                    or run["suite_id"] != job["suite_id"]
                    or run["phase"] not in ("frozen", "evaluated", "reflected")
                ):
                    raise Conflict("Experiment ownership/state changed before helper execution")
            check_source(version["source"])
            checks, outputs, log = execute(
                self.engine.runner, version, references() if job["kind"] == "check" else [job["arguments"]]
            )
            reason = "passed" if all(c["passed"] for c in checks) else "checks_failed"
        except SandboxError as exc:
            reason, outputs, log = exc.reason, exc.outputs, exc.log
        except (ValueError, SyntaxError, KeyError, Conflict) as exc:
            reason, log = "policy_or_contract_rejected", safe_error(exc)
        except Exception as exc:
            reason, log = "execution_error", safe_error(exc)
        try:
            refs = archive(self.artifacts, outputs, log, limit=version["runtime"]["artifact_bytes"])
            evidence = manifest(
                self.artifacts,
                refs,
                {
                    "tool_version": version["id"],
                    "source_sha256": version["source_sha256"],
                    "contract_id": row["contract_id"],
                    "runtime_id": digest(version["runtime"]),
                    "dependency_hash": version["dependency_hash"],
                    "implementation_id": version["implementation_id"],
                },
            ).model_dump()
            passed = reason == "passed" and bool(checks) and evidence["complete"] and not cancelled()
            if cancelled():
                reason = "cancelled"
            if not evidence["complete"]:
                reason = "artifact_quota"
            result = {
                **job,
                "status": "completed" if reason != "cancelled" else "cancelled",
                "passed": passed,
                "reason": reason,
                "checks": checks,
                "artifacts": refs,
                "manifest": evidence,
                "finished_at": now(),
            }

            def finish(current):
                if current["job"]["id"] != job["id"] or current["job"]["status"] not in (
                    "running",
                    "cancelled",
                ):
                    raise Conflict("Tool execution lease no longer held")
                result["passed"] = passed and current["job"]["status"] == "running"
                if not result["passed"] and current["job"]["status"] == "cancelled":
                    result["reason"] = "cancelled"
                versions = deepcopy(current["versions"])
                if job["kind"] == "check":
                    target = next(v for v in versions if v["id"] == version["id"])
                    target.update(
                        status="tested"
                        if result["passed"]
                        else "proposed"
                        if result["reason"]
                        in ("cancelled", "timeout", "resource_exhaustion", "unavailable_runtime")
                        else "rejected",
                        evidence=result,
                    )
                return dict(
                    versions=versions,
                    phase="cancelled"
                    if result["reason"] == "cancelled"
                    else "tested"
                    if result["passed"]
                    else "rejected",
                    job=result,
                    jobs=[*current["jobs"], result],
                )

            updated = self.store.mutate(COLLECTION, tid, finish)
            self._remember(updated, version, result)
        except Exception as exc:
            current = self.get(tid)
            if current.get("job", {}).get("id") == job["id"] and current["job"]["status"] == "running":
                self.store.update(
                    COLLECTION,
                    tid,
                    dict(
                        phase="interrupted",
                        revision=current["revision"] + 1,
                        job={
                            **job,
                            "status": "interrupted",
                            "passed": False,
                            "reason": "evidence_commit_failed",
                            "error": safe_error(exc),
                        },
                    ),
                    {"revision": current["revision"]},
                )
        finally:
            with self.engine.lock:
                self.engine.runner.cancelled = lambda: False
                self.engine.busy = False
                self.engine.release(tid)

    def _remember(self, row, version, result):
        memory = self.engine.experience
        run = memory._run(result.get("experiment_id", row["experiment_id"]))
        key = "experience-" + digest({"tool_job": result["id"], **memory.scope})
        record = memory._base(
            run,
            key,
            SourceReference(run_id=run["_id"], tool_ids=[version["id"]]),
            f"CAD plate helper {result['reason']}: {row['need']}. Construction checks do not validate design physics.",
            "tool_reference",
        )
        record.update(
            applicability=Applicability(
                domain="cad_construction", assumptions=[row["contract"]["applicability"]]
            ),
            support="hypothesis",
            local_evidence_status="harness_observed",
            confidence_basis="Independent analytic CAD construction checks only; no physical-design claim",
            attempted_change=version["summary"],
            failure_modes=[] if result["passed"] else [result["reason"]],
            tested_tools=[
                {
                    "development_id": row["_id"],
                    "version_id": version["id"],
                    "contract_id": row["contract_id"],
                    "source_sha256": version["source_sha256"],
                    "dependency_hash": version["dependency_hash"],
                    "runtime": version["runtime"],
                    "passed": result["passed"],
                    "job_id": result["id"],
                    "parent_version": version["parent_version"],
                }
            ],
            artifacts=memory._refs(
                [version["source_artifact"], version["contract_artifact"], *result["artifacts"].values()]
            ),
        )
        try:
            memory._persist(record, digest({"job": result["id"]}))
        except Exception as exc:
            self.store.event(
                run["_id"], "tool_memory_projection_pending", type(exc).__name__, tool_id=row["_id"]
            )

    def bundle(self, tid, job_id):
        row = self.get(tid)
        job = next(
            (j for j in row["jobs"] if j["id"] == job_id and j["kind"] == "invoke" and j["passed"]), None
        )
        if not job:
            raise ValueError("Candidate bundle requires a passing independently inspected invocation")
        version = self.version(row, job["version_id"])
        self.compatible(row, version)
        return {
            "title": "Plate built with tested helper",
            "change": version["summary"],
            "source": version["source"]
            + "\n\ndef build(parameters, interfaces):\n    return cq.Assembly(run(parameters))\n",
            "parameters": job["arguments"],
            "metadata": {
                "tool_development_id": tid,
                "tool_version_id": version["id"],
                "tool_job_id": job_id,
                "tool_source_sha256": version["source_sha256"],
                "tool_contract_id": row["contract_id"],
            },
        }

    def generate(self, eid, body):
        """Explicit managed reasoning; provider checkpoints/spending remain owned by the run."""
        from davinci.product.tool_contracts import ToolProposal

        self.engine.experience._run(eid)
        command = Command.model_validate(body.model_dump(include=set(Command.model_fields)))
        payload = body.model_dump(exclude=set(Command.model_fields))
        life = self.engine.lifecycle
        run, cmd, sig, done = life._begin(
            eid, command, "managed_tool_proposal", payload, {"draft", "frozen", "evaluated", "reflected"}
        )
        if run["driver"] != "managed" or run.get("managed"):
            raise Conflict(
                "Explicit tool authoring requires a manually driven managed experiment; external agents submit source directly"
            )
        if done:
            return run
        tool = self.get(body.development_id)
        if tool["actor"] != cmd.actor or tool["revision"] != body.tool_revision or not tool["contract"]:
            raise Conflict("Tool contract, owner or revision mismatch")
        if run["mode"] == "live" and not self.engine.credentials.openai_api_key:
            raise ValueError("Managed reasoning requires configured credentials")
        job = dict(
            id=identity("tool-author"), owner=cmd.actor, operation_id=cmd.operation_id, status="running"
        )
        life._execution_claim(run, cmd, sig, "managed_tool_proposal", job)
        try:
            provider = self.engine.provider_type(self.engine, run)
            answer = provider.request(
                "tool-development-" + cmd.operation_id,
                "Return source and summary strings for run(arguments), a narrowly scoped CAD construction helper. Only import cadquery as cq or math. Use Workplane/box/pushPoints/circle/extrude/cut/translate/union. No file, process or network access. No physics or scores. Fixed independent checks will run separately.",
                {
                    "need": tool["need"],
                    "contract": tool["contract"],
                    "previous": [
                        {
                            "summary": v["summary"],
                            "status": v["status"],
                            "checks": v.get("evidence", {}).get("checks", []),
                        }
                        for v in tool["versions"][-3:]
                    ],
                },
            )
            result = life._finish(eid, job["id"], {"phase": run["phase"]})
            if result["phase"] != "cancelled":
                self.propose(
                    tool["_id"],
                    ToolProposal(
                        actor=cmd.actor,
                        revision=body.tool_revision,
                        operation_id="generated-" + cmd.operation_id,
                        source=answer["source"],
                        summary=answer["summary"],
                        parent_version=tool["versions"][-1]["id"] if tool["versions"] else None,
                    ),
                )
            return result
        except Exception:
            current = life.get(eid)
            if current.get("job", {}).get("status") == "running":
                life._finish(eid, job["id"], {"phase": "interrupted", "resume_phase": run["phase"]})
            raise
        finally:
            self.engine.release(eid)
