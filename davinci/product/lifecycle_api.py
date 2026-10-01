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
    OperationStatus,
    Plan,
    PlanReadiness,
    ReferenceBuild,
    ReportExport,
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


class ReferenceBuildCommand(Command):
    reference: ReferenceBuild


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
    from davinci.product.managed_contracts import Answers, ManagedRequest
    from davinci.product.transfers import ContinueExperiment, Handoff

    api = APIRouter(prefix="/api/v2")
    life = engine.lifecycle

    @api.post("/experiments/{eid}/handoff")
    def transfer(eid: str, body: Handoff):
        from davinci.product.transfers import handoff

        return handoff(engine, eid, body)

    @api.post("/experiments/{eid}/continue", status_code=201)
    def continue_experiment(eid: str, body: ContinueExperiment):
        from davinci.product.transfers import continuation

        return continuation(engine, eid, body)

    @api.post("/managed-experiments", status_code=202)
    def managed_request(body: ManagedRequest):
        return engine.managed.workflow.start(body)

    @api.get("/test-recipes")
    def test_recipes():
        from davinci.product.recipes import catalog

        return catalog()

    @api.post("/experiments/{eid}/answers")
    def managed_answers(eid: str, body: Answers):
        return engine.managed.workflow.answer(eid, body)

    @api.get("/simulation-adapters")
    def simulation_adapters():
        from davinci.product.adapters import catalog

        return catalog()

    @api.get("/schemas")
    def schemas():
        from davinci.product.protocol import schema_catalog

        return schema_catalog()

    @api.get("/instructions")
    def instructions():
        from davinci.product.tasks import RESOURCES

        return {"version": 2, "instructions": RESOURCES.joinpath("external/AGENT.md").read_text()}

    @api.get("/runtimes/resolve")
    def resolve_runtime(image: str = Query(min_length=1, max_length=200)):
        import subprocess

        if image.startswith("-"):
            raise ValueError("Expected a Docker image name or digest")
        try:
            image_id = subprocess.check_output(
                ["docker", "image", "inspect", "--format={{.Id}}", image],
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            ).strip()
        except (OSError, subprocess.SubprocessError):
            raise ValueError(
                "Runtime unavailable; run davinci setup or build your custom Docker image"
            ) from None
        return {"version": 2, "image": image_id, "requested_image": image}

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
        row = life.get(eid)
        return {**row, "next_actions": next_actions(row)}

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

    @api.post("/experiments/{eid}/verify", status_code=202, response_model=OperationStatus)
    def verify(eid: str, body: VerificationCommand):
        return life.schedule(eid, command(body), "verify", body.verification)

    @api.post("/experiments/{eid}/reference-builds", status_code=202, response_model=OperationStatus)
    def reference_build(eid: str, body: ReferenceBuildCommand):
        return life.schedule(eid, command(body), "reference_build", body.reference)

    @api.get("/experiments/{eid}/plan-validation", response_model=PlanReadiness)
    def validate_plan(eid: str):
        return life.validate_plan(eid)

    @api.get("/experiments/{eid}/jobs/{job_id}", response_model=OperationStatus)
    def job(eid: str, job_id: str):
        result = life.job(eid, job_id)
        row = life.get(eid)
        return {
            **result,
            "result_ids": [r["id"] for r in row["results"] if r["job"]["id"] == job_id],
            "verification_ids": [v["id"] for v in row["verifications"] if v["id"] == job_id],
            "fixture_artifacts": [f["artifact"] for f in row["fixtures"] if f.get("job_id") == job_id],
            "failures": [f for f in row.get("reference_failures", []) if f["job_id"] == job_id],
            "next_actions": next_actions(row),
        }

    @api.get("/experiments/{eid}/results")
    def results(eid: str):
        row = life.get(eid)
        return {
            "version": 2,
            "results": row["results"],
            "verifications": row["verifications"],
            "reference_failures": row.get("reference_failures", []),
        }

    @api.get("/experiments/{eid}/report", response_model=ReportExport)
    def report(eid: str):
        return life.export_report(eid)

    @api.get("/experiments/{eid}/capabilities")
    def capabilities(eid: str):
        return life.capabilities(eid)

    @api.post("/experiments/{eid}/freeze")
    def freeze(eid: str, body: FreezeCommand):
        return life.freeze(eid, command(body), draft_only=body.draft_only)

    @api.post("/experiments/{eid}/candidates")
    def candidate(eid: str, body: CandidateCommand):
        return life.submit_candidate(eid, command(body), body.candidate)

    @api.post("/experiments/{eid}/evaluate", status_code=202, response_model=OperationStatus)
    def evaluate(eid: str, body: Command):
        return life.schedule(eid, body, "evaluate")

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


def next_actions(row):
    if row["driver"] == "managed" and row.get("managed") and row["phase"] not in ("cancelled", "interrupted"):
        state = row["managed"]
        return {
            "ready": ["poll_status", "inspect_evidence", "cancel"],
            "awaiting_input": ["answer_pending_questions"],
            "blocked": ["inspect_managed_error_and_capabilities", "open_linked_revision"],
            "completed": ["export_report", "inspect_experience"],
        }.get(state["status"], ["inspect_status"])
    return {
        "draft": ["update_plan", "reference_build_or_upload", "verify", "validate_plan", "freeze"],
        "awaiting_input": ["answer_pending_input", "update_plan"],
        "queued": ["poll_job", "cancel"],
        "evaluating": ["poll_job", "cancel"],
        "verifying": ["poll_job", "cancel"],
        "frozen": ["submit_candidate"],
        "candidate_submitted": ["evaluate"],
        "evaluated": ["inspect_results", "reflect"],
        "reflected": ["submit_candidate", "finalize"],
        "completed": ["export_report", "revise"],
        "interrupted": ["inspect_job", "resume_or_revise"],
        "cancelled": ["inspect_job", "resume_or_revise"],
    }.get(row.get("phase"), ["inspect_status"])
