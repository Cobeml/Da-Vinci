"""Local JSON contracts for the v2 lifecycle (same host/origin boundary as v1)."""

import base64
import binascii
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import Field

from davinci.product.contracts import (
    Candidate,
    Command,
    Evaluator,
    OpenExperiment,
    Plan,
    Runtime,
    Verification,
)


class PlanCommand(Command):
    plan: Plan
    evaluator: Evaluator | None = None
    runtime: Runtime | None = None


class FixtureCommand(Command):
    step_base64: str = Field(max_length=43_000_000)
    provenance: str = Field(min_length=1, max_length=4000)


class VerificationCommand(Command):
    verification: Verification


class FreezeCommand(Command):
    draft_only: bool = False


class CandidateCommand(Command):
    candidate: Candidate


class ReflectionCommand(Command):
    lesson: str = Field(min_length=1, max_length=4000)
    result_id: str | None = None


def command(body):
    return Command.model_validate(body.model_dump(include={"actor", "revision", "operation_id"}))


def router(engine):
    api = APIRouter(prefix="/api/v2")
    life = engine.lifecycle

    @api.post("/experiments", status_code=201)
    def open_experiment(body: OpenExperiment):
        return life.open(body)

    @api.get("/experiments")
    def experiments():
        return [
            {k: row[k] for k in ("_id", "object_id", "description", "phase", "revision", "driver", "mode")}
            for row in engine.store.list("runs", {"lifecycle_version": 2}, limit=10000)
        ]

    @api.get("/experience")
    def retrieve(q: str = Query(max_length=12000), experiment_id: str | None = None):
        return life.retrieve(q, experiment_id=experiment_id)

    @api.get("/experiments/{eid}")
    def detail(eid: str):
        return life.get(eid)

    @api.post("/experiments/{eid}/plan")
    def plan(eid: str, body: PlanCommand):
        return life.update_plan(eid, command(body), body.plan, body.evaluator, body.runtime)

    @api.post("/experiments/{eid}/fixtures")
    def fixture(eid: str, body: FixtureCommand):
        try:
            step = base64.b64decode(body.step_base64, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("Invalid base64 STEP") from None
        return life.fixture(eid, command(body), step=step, provenance=body.provenance)

    @api.post("/experiments/{eid}/verify")
    def verify(eid: str, body: VerificationCommand):
        return life.verify(eid, command(body), body.verification)

    @api.get("/experiments/{eid}/capabilities")
    def capabilities(eid: str):
        return life.capabilities(eid)

    @api.post("/experiments/{eid}/freeze")
    def freeze(eid: str, body: FreezeCommand):
        return life.freeze(eid, command(body), draft_only=body.draft_only)

    @api.post("/experiments/{eid}/candidates")
    def candidate(eid: str, body: CandidateCommand):
        return life.submit_candidate(eid, command(body), body.candidate)

    @api.post("/experiments/{eid}/evaluate")
    def evaluate(eid: str, body: Command):
        return life.request_evaluation(eid, body)

    @api.post("/experiments/{eid}/reflections")
    def reflect(eid: str, body: ReflectionCommand):
        return life.reflect(eid, command(body), lesson=body.lesson, result_id=body.result_id)

    @api.post("/experiments/{eid}/finalize")
    def finalize(eid: str, body: Command):
        return life.finalize(eid, body)

    @api.post("/experiments/{eid}/cancel")
    def cancel(eid: str, body: Command):
        return life.cancel(eid, body)

    @api.post("/experiments/{eid}/resume")
    def resume(eid: str, body: Command):
        return life.resume(eid, body)

    @api.post("/experiments/{eid}/revisions", status_code=201)
    def revise(eid: str, body: OpenExperiment):
        return life.revise(eid, body)

    @api.post("/experiments/{eid}/managed/{stage}")
    def managed(eid: str, stage: Literal["author", "propose", "reflect"], body: Command):
        return engine.managed.advance(eid, body, stage)

    return api
