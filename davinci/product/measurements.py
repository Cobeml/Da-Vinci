"""Immutable, attributed physical observations with separate calibration partitions.

This service never writes runs, simulation results, accepted scores or evaluators.
"""

import base64
import hashlib
import json
from statistics import mean

from davinci.models import digest, now
from davinci.product.lifecycle import Conflict
from davinci.product.measurement_contracts import MeasurementInput
from davinci.product.units import convert

COLLECTION = "attributed_evidence_v1"


class Measurements:
    def __init__(self, engine):
        self.engine, self.store, self.artifacts = engine, engine.store, engine.artifacts
        self.scope = engine.experience.scope

    def get(self, key):
        row = self.store.get(COLLECTION, key)
        if not row or any(row.get(k) != v for k, v in self.scope.items()):
            raise KeyError("Evidence not found in current workspace/project")
        return row

    def _key(self, body):
        return "attributed-" + digest({**self.scope, "actor": body.actor, "operation": body.operation_id})

    def _prior(self, body, kind):
        row = self.store.get(COLLECTION, self._key(body))
        if row and (row.get("signature") != digest(body.model_dump(mode="json")) or row["kind"] != kind):
            raise Conflict("Evidence operation reused with different content")
        return row

    def _save(self, body, kind, payload):
        row = dict(
            _id=self._key(body),
            **self.scope,
            created_at=now(),
            kind=kind,
            actor=body.actor,
            operation_id=body.operation_id,
            signature=digest(body.model_dump(mode="json")),
            origin=self.scope,
            trust="attributed_not_authenticated",
            changes_design_acceptance=False,
            **payload,
        )
        row["record_sha256"] = digest(row)
        if not self.store.insert(COLLECTION, row):
            return self._prior(body, kind)
        return row

    def _artifacts(self, blobs):
        total = 0
        for blob in blobs:
            data = base64.b64decode(blob.data_base64, validate=True)
            total += len(data)
            if (
                total > 12_000_000
                or len(data) != blob.size
                or hashlib.sha256(data).hexdigest() != blob.sha256
                or blob.artifact_id != "artifact-" + blob.sha256
            ):
                raise ValueError("Invalid or excessive evidence artifact content")
            self.artifacts.put(data, blob.name, blob.media_type)

    def record(self, body):
        if prior := self._prior(body, "measurement"):
            return prior
        m = body.measurement
        run = self.engine.experience._run(m.specimen.cad.experiment_id)
        if run.get("lifecycle_version") != 2:
            raise ValueError("Measurement links currently require v2 evidence")
        result = next(
            (
                r
                for r in run["results"]
                if r["id"] == m.specimen.cad.result_id and r["candidate_id"] == m.specimen.cad.candidate_id
            ),
            None,
        )
        if not result or not result["artifacts"].get("model.step"):
            raise ValueError("Specimen must link to an actual evaluated/exported CAD revision")
        for aid, checksum in [
            (result["artifacts"]["model.step"], m.specimen.cad.geometry_sha256),
            (result["source_artifact"], m.specimen.cad.source_sha256),
        ]:
            meta = self.store.get("artifacts", aid)
            if not meta or meta["sha256"] != checksum:
                raise ValueError("Specimen CAD/source identity does not match stored evidence")
            self.artifacts.verify(aid)
        if m.supersedes:
            old = self.get(m.supersedes)
            if (
                old["kind"] != "measurement"
                or old["input"]["specimen"] != m.specimen.model_dump(mode="json")
                or old["input"]["partition"] != m.partition
            ):
                raise ValueError("Correction must retain specimen and partition")
        self._artifacts(body.artifacts)
        for aid in m.raw_artifact_ids:
            self.artifacts.verify(aid)
        # One immutable allocation per declared specimen prevents fitting held-out samples.
        key = "specimen-" + digest({**self.scope, "specimen": m.specimen.specimen_id})
        allocation = dict(
            _id=key,
            **self.scope,
            specimen=m.specimen.model_dump(mode="json"),
            partition=m.partition,
            evidence_kind=m.evidence_kind,
        )
        if not self.store.insert("measurement_specimens_v1", allocation):
            if self.store.get("measurement_specimens_v1", key) != allocation:
                raise Conflict("Specimen identity/material/process/partition already allocated differently")
        comparison = None
        if m.prediction:
            test = next((t for t in result["tests"] if t["test_id"] == m.prediction.test_id), None)
            if (
                not test
                or test["status"] not in ("pass", "physical_failure")
                or not result["evidence_complete"]
            ):
                raise ValueError("Comparison requires complete, applicable prediction evidence")
            prediction = test["metrics"].get(m.prediction.metric)
            if not prediction:
                raise ValueError("Prediction metric not present")
            measured = convert(m.quantity.value, m.quantity.unit, prediction["unit"], m.quantity.dimension)
            uncertainty = convert(
                m.quantity.uncertainty, m.quantity.unit, prediction["unit"], m.quantity.dimension
            )
            comparison = dict(
                predicted=prediction["value"],
                observed=measured,
                unit=prediction["unit"],
                residual=measured - prediction["value"],
                observation_uncertainty=uncertainty,
                prediction_numerical_error=prediction["numerical_error"],
                prediction_uncertainty=prediction["uncertainty"],
                uncertainty_interpretation="Components retained separately; no independence/coverage probability assumed",
                metric=m.prediction.metric,
                test_id=m.prediction.test_id,
                **{k: result[k] for k in ("suite_id", "evaluator_id", "runtime_id", "execution_id")},
            )
        context = dict(
            material=m.specimen.material,
            process=m.specimen.process,
            setup=m.setup.model_dump(mode="json"),
            evidence_kind=m.evidence_kind,
            uncertainty_kind=m.quantity.uncertainty_kind,
            coverage_factor=m.quantity.coverage_factor,
            prediction={
                k: comparison[k]
                for k in (
                    "unit",
                    "metric",
                    "test_id",
                    "suite_id",
                    "evaluator_id",
                    "runtime_id",
                    "execution_id",
                )
            }
            if comparison
            else None,
        )
        observation_artifact = self.artifacts.put(
            m.model_dump_json().encode(), "attributed-measurement.json", "application/json"
        )
        saved = self._save(
            body,
            "measurement",
            dict(
                input=m.model_dump(mode="json"),
                comparison=comparison,
                context=context,
                context_id=digest(context),
                link_status="local_CAD_identity_verified",
                artifacts=[
                    observation_artifact,
                    *m.raw_artifact_ids,
                    result["artifacts"]["model.step"],
                    result["source_artifact"],
                ],
            ),
        )
        # Searchable attributed observations remain hypotheses about physical validity.
        from davinci.product.memory_contracts import SourceReference

        memory = self.engine.experience
        key = "experience-" + digest({"measurement": saved["_id"], **self.scope})
        record = memory._base(
            run,
            key,
            SourceReference(run_id=run["_id"], candidate_id=result["candidate_id"], result_id=result["id"]),
            f"Attributed {m.evidence_kind}: {m.quantity_name}={m.quantity.value} {m.quantity.unit} for specimen {m.specimen.specimen_id}; not authenticated laboratory evidence or design acceptance.",
            "observation",
        )
        record.update(
            support="hypothesis",
            local_evidence_status="unverified",
            confidence_basis="Source attribution supplied by importer; CAD linkage checked, physical authenticity not established",
            measured_outcomes=[
                {
                    "attributed_measurement_id": saved["_id"],
                    "record_sha256": saved["record_sha256"],
                    "quantity": m.quantity.model_dump(),
                    "evidence_kind": m.evidence_kind,
                }
            ],
            artifacts=memory._refs(saved["artifacts"]),
            evidence_issues=["Physical authenticity not independently verified"],
        )
        try:
            memory._persist(record, digest({"measurement": saved["_id"]}))
        except Exception as exc:
            self.store.event(run["_id"], "measurement_memory_pending", type(exc).__name__)
        return saved

    def _measurements(self, ids, partition):
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate measurement IDs")
        rows = [self.get(i) for i in ids]
        if any(
            r["kind"] != "measurement"
            or r.get("link_status") != "local_CAD_identity_verified"
            or not r.get("comparison")
            or r["input"]["partition"] != partition
            for r in rows
        ):
            raise ValueError(
                "Requires locally linked comparable observations from the declared partition; imported claims cannot fit a calibration"
            )
        specimens = [r["input"]["specimen"]["specimen_id"] for r in rows]
        if len(set(specimens)) != len(specimens):
            raise ValueError("One observation per specimen per calibration/validation operation")
        if len({r["context_id"] for r in rows}) != 1:
            raise ValueError(
                "Material/process/setup/suite/runtime/metric or uncertainty interpretation differs"
            )
        for r in rows:
            for aid in r["artifacts"]:
                self.artifacts.verify(aid)
        return rows

    def fit(self, body):
        if prior := self._prior(body, "calibration"):
            return prior
        rows = self._measurements(body.measurement_ids, "calibration")
        previous = self.get(body.predecessor_id) if body.predecessor_id else None
        if previous and (
            previous["kind"] != "calibration"
            or previous.get("link_status") != "local_fit"
            or previous["context_id"] != rows[0]["context_id"]
            or previous["name"] != body.name
        ):
            raise ValueError("Calibration predecessor family/context mismatch")
        offset = mean(r["comparison"]["residual"] for r in rows)
        return self._save(
            body,
            "calibration",
            dict(
                name=body.name,
                method=body.method,
                version=previous["version"] + 1 if previous else 1,
                predecessor_id=body.predecessor_id,
                measurement_ids=body.measurement_ids,
                specimen_ids=[r["input"]["specimen"]["specimen_id"] for r in rows],
                context_id=rows[0]["context_id"],
                context=rows[0]["context"],
                offset=offset,
                unit=rows[0]["comparison"]["unit"],
                calibration_mae=mean(abs(r["comparison"]["residual"] - offset) for r in rows),
                uncertainty_note="Descriptive offset only; fit residual is not predictive uncertainty or validation evidence",
                applicability=body.applicability,
                link_status="local_fit",
                artifacts=[],
            ),
        )

    def validate(self, body):
        if prior := self._prior(body, "calibration_validation"):
            return prior
        fit = self.get(body.calibration_id)
        if fit["kind"] != "calibration" or fit.get("link_status") != "local_fit":
            raise ValueError("Imported calibration is not a locally reproduced fit")
        rows = self._measurements(body.measurement_ids, "held_out_validation")
        if rows[0]["context_id"] != fit["context_id"] or set(fit["specimen_ids"]) & {
            r["input"]["specimen"]["specimen_id"] for r in rows
        }:
            raise ValueError("Held-out context mismatch or calibration specimen leakage")
        comparisons = [
            dict(
                measurement_id=r["_id"],
                before=r["comparison"]["residual"],
                after=r["comparison"]["residual"] - fit["offset"],
                observation_uncertainty=r["comparison"]["observation_uncertainty"],
            )
            for r in rows
        ]
        return self._save(
            body,
            "calibration_validation",
            dict(
                calibration_id=fit["_id"],
                calibration_sha256=fit["record_sha256"],
                measurement_ids=body.measurement_ids,
                comparisons=comparisons,
                mae_before=mean(abs(c["before"]) for c in comparisons),
                mae_after=mean(abs(c["after"]) for c in comparisons),
                unit=fit["unit"],
                evidence_kind=rows[0]["input"]["evidence_kind"],
                interpretation="Held-out descriptive comparison only; no automatic solver correction or design acceptance",
                artifacts=[],
            ),
        )

    def export(self, body):
        records = []
        pending = list(body.ids)
        while pending:
            row = self.get(pending.pop())
            if row["_id"] in {r["_id"] for r in records}:
                continue
            records.append(row)
            if len(records) > 100:
                raise ValueError("Export closure exceeds 100 records")
            pending.extend(row.get("measurement_ids", []))
            pending.extend([row[k] for k in ("calibration_id", "predecessor_id") if row.get(k)])
        blobs = []
        total = 0
        if body.include_artifacts:
            for aid in sorted({a for r in records for a in r.get("artifacts", [])}):
                meta = self.store.get("artifacts", aid)
                total += meta["size"]
                if total > 12_000_000:
                    raise ValueError("Export too large; export references only")
                blobs.append(
                    dict(
                        artifact_id=aid,
                        **{k: meta[k] for k in ("sha256", "size", "name", "media_type")},
                        data_base64=base64.b64encode(self.artifacts.read(aid)).decode(),
                    )
                )
        return dict(version=1, origin=self.scope, records=records, artifacts=blobs)

    def restore(self, body):
        if prior := self._prior(body, "import"):
            return prior
        if len(json.dumps(body.model_dump(mode="json")).encode()) > 20_000_000:
            raise ValueError("Evidence bundle exceeds 20MB")
        for record in body.bundle.records:
            if digest({k: v for k, v in record.items() if k != "record_sha256"}) != record.get(
                "record_sha256"
            ):
                raise ValueError("Portable record checksum mismatch (not an authenticity proof)")
            if record.get("kind") == "measurement":
                MeasurementInput.model_validate(record["input"])
        self._artifacts(body.bundle.artifacts)
        items = []
        for record in body.bundle.records:
            issues = []
            for aid in record.get("artifacts", []):
                try:
                    self.artifacts.verify(aid)
                except (ValueError, KeyError, OSError):
                    issues.append("Missing or corrupted artifact: " + aid)
            key = "imported-evidence-" + digest(
                {**self.scope, "operation": self._key(body), "source": record["_id"]}
            )
            row = dict(
                _id=key,
                **self.scope,
                created_at=now(),
                kind="imported_record",
                origin=body.bundle.origin,
                origin_record=record,
                link_status="imported_unverified",
                trust="attributed_not_authenticated",
                evidence_issues=issues,
                changes_design_acceptance=False,
                artifacts=record.get("artifacts", []),
            )
            row["record_sha256"] = digest(row)
            self.store.insert(COLLECTION, row)
            items.append(key)
        return self._save(body, "import", dict(items=items, artifacts=[], locally_reproduced=False))
