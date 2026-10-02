"""Both drivers use the same validated tool-development operations."""

from fastapi import APIRouter

from davinci.product.contracts import Command
from davinci.product.tool_contracts import (
    ManagedToolProposal,
    ToolDefinition,
    ToolInvocation,
    ToolNeed,
    ToolPin,
    ToolPromotion,
    ToolProposal,
    ToolVersionCommand,
)
from davinci.product.tool_execution import descriptor


def router(engine):
    api = APIRouter(prefix="/api/v2")
    service = engine.tool_learning

    @api.get("/tools/classes")
    def classes():
        return [descriptor()]

    @api.get("/tools")
    def browse():
        return service.catalog()

    @api.post("/tools", status_code=201)
    def open_tool(body: ToolNeed):
        return service.open(body)

    @api.get("/tools/{tid}")
    def status(tid: str):
        return service.get(tid)

    @api.post("/tools/{tid}/define")
    def define(tid: str, body: ToolDefinition):
        return service.define(tid, body)

    @api.post("/tools/{tid}/propose")
    def propose(tid: str, body: ToolProposal):
        return service.propose(tid, body)

    @api.post("/tools/{tid}/check", status_code=202)
    def check(tid: str, body: ToolVersionCommand):
        return service.check(tid, body)

    @api.post("/tools/{tid}/promote")
    def promote(tid: str, body: ToolPromotion):
        return service.promote(tid, body)

    @api.post("/tools/{tid}/rollback")
    def rollback(tid: str, body: ToolPromotion):
        return service.promote(tid, body, rollback=True)

    @api.post("/tools/{tid}/invoke", status_code=202)
    def invoke(tid: str, body: ToolInvocation):
        return service.invoke(tid, body)

    @api.post("/tools/{tid}/cancel")
    def cancel(tid: str, body: Command):
        return service.cancel(tid, body)

    @api.get("/tools/{tid}/bundles/{job_id}")
    def bundle(tid: str, job_id: str):
        return service.bundle(tid, job_id)

    @api.post("/experiments/{eid}/tool-pins")
    def pin(eid: str, body: ToolPin):
        return service.pin(eid, body)

    @api.post("/experiments/{eid}/tool-proposals")
    def generate(eid: str, body: ManagedToolProposal):
        return service.generate(eid, body)

    return api
