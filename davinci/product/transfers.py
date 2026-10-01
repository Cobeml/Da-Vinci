"""Explicit idle-checkpoint ownership transfer and same-suite continuation."""

from copy import deepcopy
from typing import Literal

from pydantic import Field

from davinci.models import digest, now
from davinci.product.contracts import Candidate, Command, OpenExperiment
from davinci.product.lifecycle import Conflict
from davinci.product.managed_contracts import SearchPolicy


class Handoff(Command):
    driver: Literal["managed", "external"]
    new_actor: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)
    policy: SearchPolicy = Field(default_factory=SearchPolicy)


class ContinueExperiment(Command):
    candidate_id: str
    driver: Literal["managed", "external"]
    new_actor: str = Field(min_length=1, max_length=100)
    budget_usd: float = Field(default=10, gt=0, le=1000)
    focus: str = Field(default="", max_length=2000)
    policy: SearchPolicy = Field(default_factory=SearchPolicy)


IDLE = {"frozen", "candidate_submitted", "evaluated", "reflected", "completed"}


def idle(engine, row):
    if row["phase"] not in IDLE or (row.get("job") or {}).get("status") in {"queued", "running"}:
        raise Conflict("Cancel/finish active work and reach a frozen idle checkpoint before transferring")
    if engine.store.get("pointers", "product-active-run")["run_id"] == row["_id"]:
        raise Conflict("Execution owner has not released this experiment")
    engine.lifecycle._context(row)  # includes immutable execution identity


def managed_state(engine, row, policy, previous=None):
    if row["mode"] == "live" and not engine.credentials.openai_api_key:
        raise ValueError("Configure generation credentials on the server before selecting the managed driver")
    if row["draft_only"]:
        raise ValueError("Automatic managed continuation requires a verified frozen suite, not a draft")
    source = None
    if row["candidates"]:
        source = engine.artifacts.read(row["candidates"][-1]["source_artifact"]).decode()
    if source is None:
        fixture = next((f for f in row["fixtures"] if f.get("source_artifact")), None)
        source = engine.artifacts.read(fixture["source_artifact"]).decode() if fixture else None
    if source is None:
        raise ValueError("Managed adoption needs an inspectable candidate or reference builder")
    previous = previous or {}
    if policy.search == "coordinate" and not previous.get("requirements"):
        raise ValueError("Use agent search for an adopted suite without a verified optimization recipe")
    stage = {
        "frozen": "propose",
        "candidate_submitted": "simulate",
        "evaluated": "diagnose",
        "reflected": "propose",
    }[row["phase"]]
    # Keep cumulative resource charges and an epoch distinct from every former managed driver.
    return {
        "version": 1,
        "stage": stage,
        "status": "ready",
        "epoch": previous.get("epoch", 0) + 1,
        "iteration": 0,
        "policy": policy.model_dump(),
        "runtime": row["runtime"],
        "answers": previous.get("answers", []),
        "outputs": {},
        "experience": [],
        "existing": None,
        "repair": 0,
        "setup_repairs": 0,
        "fixture_index": 0,
        "solver_reservations": previous.get("solver_reservations", {}),
        "stop_reason": None,
        "final_result_id": None,
        "references": [{"candidate": {"source": source}}],
        "adopted_frozen_suite": row["suite_id"],
        "requirements": previous.get("requirements"),
        "session_candidate_start": len(row["candidates"]),
        "session_result_start": len(row["results"]),
    }


def handoff(engine, eid, body):
    engine.experience._run(eid)
    body = Handoff.model_validate(body)
    life = engine.lifecycle
    payload = body.model_dump(exclude={"actor", "revision", "operation_id"})
    command = Command.model_validate(body.model_dump(include=set(Command.model_fields)))
    with engine.lock:
        current = life.get(eid)
        signature = digest({"action": "handoff", "payload": payload, "actor": body.actor})
        receipt = current["operations"].get(body.operation_id)
        # Retrying the completed transfer by its former owner is read-only and idempotent.
        if receipt:
            if receipt["signature"] != signature:
                raise Conflict("Handoff operation reused with different content")
            return current
        row, cmd, sig, _ = life._begin(eid, command, "handoff", payload, IDLE - {"completed"})
        idle(engine, row)
        if body.driver == row["driver"] and body.new_actor == row["actor"]:
            raise ValueError("Driver/owner are unchanged")
        state = row.get("managed")
        if body.driver == "managed":
            state = managed_state(engine, row, body.policy, state)
        elif state:
            state = {**state, "status": "handed_off"}
        history = [
            *row.get("handoffs", []),
            {
                "at": now(),
                "from_driver": row["driver"],
                "from_actor": row["actor"],
                "to_driver": body.driver,
                "to_actor": body.new_actor,
                "reason": body.reason,
                "suite_id": row["suite_id"],
                "operation_id": body.operation_id,
            },
        ]
        return life._commit(
            row,
            cmd,
            sig,
            "handoff",
            {
                "driver": body.driver,
                "actor": body.new_actor,
                "managed": state,
                "handoffs": history,
                "ownership_epoch": row.get("ownership_epoch", 0) + 1,
            },
        )


def continuation(engine, eid, body):
    engine.experience._run(eid)
    body = ContinueExperiment.model_validate(body)
    life = engine.lifecycle
    payload = body.model_dump(exclude={"actor", "revision", "operation_id"})
    command = Command.model_validate(body.model_dump(include=set(Command.model_fields)))
    with engine.lock:
        row, cmd, sig, done = life._begin(eid, command, "continue_experiment", payload, IDLE)
        idle(engine, row)
        seed = next((c for c in row["candidates"] if c["id"] == body.candidate_id), None)
        if not seed:
            raise ValueError("Choose a candidate belonging to this experiment")
        for aid in [row["suite_artifact"], row["execution_artifact"], seed["source_artifact"]]:
            engine.artifacts.verify(aid)
        if body.driver == "managed":
            managed_state(engine, {**row, "phase": "candidate_submitted"}, body.policy)
        if not done:
            # Persist the parent receipt first; deterministic child identity makes crash recovery retryable.
            life._commit(row, cmd, sig, "continue_experiment", {})
        request = OpenExperiment(
            object=row["opening"]["object"],
            description=row["description"]
            + ("\nContinuation focus (frozen requirements unchanged): " + body.focus if body.focus else ""),
            driver=body.driver,
            mode=row["mode"],
            actor=body.new_actor,
            operation_id="continue-" + digest({"parent": eid, "operation": body.operation_id})[:24],
            parent_experiment_id=eid,
            budget_usd=body.budget_usd,
            metadata={"continuation": payload, "source_suite_id": row["suite_id"]},
        )
        child = life.open(request)
        if child["revision"] == 0:
            fields = {
                k: deepcopy(row[k])
                for k in (
                    "plan",
                    "plan_id",
                    "evaluator",
                    "evaluator_id",
                    "runtime",
                    "runtime_id",
                    "execution_id",
                    "suite_id",
                    "suite_artifact",
                    "execution_artifact",
                    "plan_revisions",
                    "fixtures",
                    "verifications",
                    "coverage",
                    "capabilities",
                    "validation_gaps",
                    "frozen_at",
                    "draft_only",
                )
            }
            fields.update(
                phase="frozen",
                status="active",
                continuation={
                    "experiment_id": eid,
                    "candidate_id": seed["id"],
                    "suite_id": row["suite_id"],
                    "focus": body.focus,
                    "verification_origin": eid,
                    "results_inherited": False,
                },
            )
            c = Command(actor=child["actor"], revision=0, operation_id="inherit-frozen-suite")
            _, c, sign, _ = life._begin(child["_id"], c, "inherit_frozen_suite", fields)
            child = life._commit(child, c, sign, "inherit_frozen_suite", fields)
        if not child["candidates"]:
            source = engine.artifacts.read(seed["source_artifact"]).decode()
            child = life.submit_candidate(
                child["_id"],
                Command(actor=child["actor"], revision=child["revision"], operation_id="continuation-seed"),
                Candidate(
                    title=seed["title"],
                    change=seed["change"],
                    source=source,
                    parameters=seed["parameters"],
                    metadata=seed.get("metadata", {}),
                ),
            )
        if body.driver == "managed" and not child.get("managed"):
            state = managed_state(engine, child, body.policy)
            state["session_candidate_start"] = 0
            c = Command(actor=child["actor"], revision=child["revision"], operation_id="continue-managed")
            _, c, sign, _ = life._begin(child["_id"], c, "continue_managed", state)
            child = life._commit(child, c, sign, "continue_managed", {"managed": state})
        return child
