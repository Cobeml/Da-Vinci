"""Public attributed evidence operations, shared by both drivers."""

from fastapi import APIRouter, Query

from davinci.product.measurement_contracts import (
    CalibrationFit,
    CalibrationValidation,
    EvidenceExport,
    EvidenceRestore,
    RecordMeasurement,
)


def router(engine):
    api = APIRouter(prefix="/api/v2/evidence")
    service = engine.measurements

    @api.get("")
    def browse(
        after_id: str = Query(default="", max_length=200), limit: int = Query(default=50, ge=1, le=100)
    ):
        rows = engine.store.scoped_page(
            "attributed_evidence_v1", service.scope, after_id=after_id, limit=limit + 1
        )
        return {"items": rows[:limit], "next_cursor": rows[limit - 1]["_id"] if len(rows) > limit else None}

    @api.post("/measurements", status_code=201)
    def record(body: RecordMeasurement):
        return service.record(body)

    @api.post("/calibrations", status_code=201)
    def calibrate(body: CalibrationFit):
        return service.fit(body)

    @api.post("/validations", status_code=201)
    def validate(body: CalibrationValidation):
        return service.validate(body)

    @api.post("/export")
    def export(body: EvidenceExport):
        return service.export(body)

    @api.post("/import", status_code=201)
    def restore(body: EvidenceRestore):
        return service.restore(body)

    @api.get("/{record_id}")
    def inspect(record_id: str):
        return service.get(record_id)

    return api
