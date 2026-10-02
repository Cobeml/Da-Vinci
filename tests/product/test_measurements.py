"""All observations in this file are explicitly synthetic, never lab measurements."""

import copy

import pytest
from fastapi.testclient import TestClient
from test_external import ForbiddenProvider, mutate, open_experiment, prepare, wait
from test_lifecycle import FixtureRunner, candidate

from davinci.config import Settings
from davinci.product.api import create_app
from davinci.product.engine import Engine


def synthetic(row, index, partition="calibration", residual=0.2, unit="g"):
    result = row["results"][-1]
    prediction = result["tests"][0]["metrics"]["mass_g"]["value"]
    return dict(
        actor="measurement-importer",
        operation_id=f"synthetic-{index}",
        measurement=dict(
            specimen=dict(
                specimen_id=f"SYNTHETIC-{index}",
                cad=dict(
                    experiment_id=row["_id"],
                    candidate_id=result["candidate_id"],
                    result_id=result["id"],
                    geometry_sha256=result["artifacts"]["model.step"].removeprefix("artifact-"),
                    source_sha256=result["source_artifact"].removeprefix("artifact-"),
                ),
                material=dict(
                    name="Synthetic aluminium",
                    source="Test fixture, no physical sample",
                    batch="synthetic-batch",
                ),
                process=dict(method="synthetic", source="Automated software fixture"),
            ),
            partition=partition,
            evidence_kind="synthetic_fixture",
            quantity_name="mass",
            quantity=dict(
                value=(prediction + residual) * (0.001 if unit == "kg" else 1),
                unit=unit,
                dimension="mass",
                uncertainty=0.01 * (0.001 if unit == "kg" else 1),
                uncertainty_basis="Synthetic interval for software checks only",
                uncertainty_kind="interval_half_width",
            ),
            setup=dict(
                id="synthetic-scale",
                revision="1",
                description="Synthetic balance comparison, no hardware",
                instruments=["synthetic numerical fixture"],
                source="test_measurements.py",
            ),
            measured_at="2026-01-01T12:00:00+00:00",
            attribution="Automated synthetic fixture",
            source="Synthetic software test; not laboratory data",
            prediction=dict(
                test_id="beam",
                metric="mass_g",
                comparability_basis="Synthetic mass quantity constructed to match the nominal simulation definition",
            ),
        ),
    )


@pytest.fixture
def evidence(tmp_path):
    engine = Engine(
        tmp_path,
        runner=FixtureRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
    )
    with TestClient(create_app(tmp_path, engine=engine)) as client:
        row = prepare(client, open_experiment(client))
        mutate(client, row["_id"], "candidates", "candidate", {"candidate": candidate(4).model_dump()})
        job = mutate(client, row["_id"], "evaluate", "eval")
        wait(client, row["_id"], job)
        yield client, client.get("/api/v2/experiments/" + row["_id"]).json(), engine


def post(client, path, body, code=201):
    response = client.post("/api/v2/evidence/" + path, json=body)
    assert response.status_code == code, response.text
    return response.json()


def test_synthetic_comparison_calibration_and_held_out_separation(evidence):
    client, row, engine = evidence
    fitted = [
        post(client, "measurements", synthetic(row, i, residual=x, unit="kg" if i == 0 else "g"))
        for i, x in enumerate((0.1, 0.2, 0.3))
    ]
    ids = [r["_id"] for r in fitted]
    assert fitted[0]["comparison"]["residual"] == pytest.approx(0.1)
    held = [
        post(client, "measurements", synthetic(row, i, "held_out_validation", x))
        for i, x in [(3, 0.2), (4, 0.25)]
    ]
    body = dict(
        actor="calibrator",
        operation_id="fit",
        name="synthetic-scale-offset",
        measurement_ids=ids,
        applicability="Synthetic fixed setup and material, no real calibration claim",
    )
    fit = post(client, "calibrations", body)
    assert fit["offset"] == pytest.approx(0.2)
    assert post(client, "calibrations", body)["_id"] == fit["_id"]
    check = post(
        client,
        "validations",
        dict(
            actor="calibrator",
            operation_id="validate",
            calibration_id=fit["_id"],
            measurement_ids=[r["_id"] for r in held],
        ),
    )
    assert check["mae_after"] < check["mae_before"]
    assert check["evidence_kind"] == "synthetic_fixture"
    post(
        client,
        "calibrations",
        {**body, "operation_id": "leak", "measurement_ids": [ids[0], ids[1], held[0]["_id"]]},
        422,
    )
    post(
        client,
        "validations",
        dict(
            actor="calibrator", operation_id="train-as-test", calibration_id=fit["_id"], measurement_ids=ids
        ),
        422,
    )
    changed = synthetic(row, 0, "held_out_validation")
    changed["operation_id"] = "relabel"
    post(client, "measurements", changed, 409)
    revision = post(client, "calibrations", {**body, "operation_id": "fit-v2", "predecessor_id": fit["_id"]})
    assert revision["version"] == 2 and revision["predecessor_id"] == fit["_id"]
    assert client.get("/api/v2/experiments/" + row["_id"]).json() == row
    assert not engine.store.list("requests")
    notes = engine.store.list("experiences_v1")
    assert all(r["support"] != "measurement_supported" for r in notes)


def test_measurement_identity_units_provenance_and_invalid_inputs(evidence):
    client, row, _ = evidence
    for change in ("geometry", "units", "date", "uncertainty", "extra"):
        body = synthetic(row, change)
        if change == "geometry":
            body["measurement"]["specimen"]["cad"]["geometry_sha256"] = "0" * 64
        if change == "units":
            body["measurement"]["quantity"]["unit"] = "MPa"
        if change == "date":
            body["measurement"]["measured_at"] = "2026-01-01T12:00:00"
        if change == "uncertainty":
            body["measurement"]["quantity"]["uncertainty"] = -1
        if change == "extra":
            body["measurement"]["design_accepted"] = True
        post(client, "measurements", body, 422)
    good = synthetic(row, "valid")
    original = post(client, "measurements", good)
    assert post(client, "measurements", good)["_id"] == original["_id"]
    altered = copy.deepcopy(good)
    altered["measurement"]["quantity"]["value"] += 1
    post(client, "measurements", altered, 409)


def test_measurement_export_import_preserves_attribution_not_local_trust(evidence):
    client, row, engine = evidence
    records = [post(client, "measurements", synthetic(row, i)) for i in range(3)]
    fit = post(
        client,
        "calibrations",
        dict(
            actor="calibrator",
            operation_id="fit",
            name="synthetic",
            measurement_ids=[r["_id"] for r in records],
            applicability="Synthetic fixture calibration comparison only",
        ),
    )
    bundle = post(client, "export", dict(ids=[fit["_id"]], include_artifacts=True), 200)
    assert len(bundle["records"]) == 4
    restored = post(client, "import", dict(actor="importer", operation_id="restore", bundle=bundle))
    imported = [client.get("/api/v2/evidence/" + i).json() for i in restored["items"]]
    assert all(r["link_status"] == "imported_unverified" and not r["evidence_issues"] for r in imported)
    post(
        client,
        "calibrations",
        dict(
            actor="calibrator",
            operation_id="invalid-refit",
            name="synthetic",
            measurement_ids=restored["items"][:3],
            applicability="Cannot fit unverified imported records",
        ),
        422,
    )
    tampered = copy.deepcopy(bundle)
    tampered["records"][0]["name"] = "forged"
    post(client, "import", dict(actor="importer", operation_id="tampered", bundle=tampered), 422)
    engine.experience.scope["project_id"] = "another-project"
    assert client.get("/api/v2/evidence/" + fit["_id"]).status_code == 404


def test_calibration_negative_transfer_and_setup_mismatch(evidence):
    client, row, _ = evidence
    train = [post(client, "measurements", synthetic(row, i, residual=0.2))["_id"] for i in range(3)]
    fit = post(
        client,
        "calibrations",
        dict(
            actor="calibrator",
            operation_id="fit",
            name="synthetic",
            measurement_ids=train,
            applicability="Synthetic fixture comparison; no performance guarantee",
        ),
    )
    held = post(client, "measurements", synthetic(row, 3, "held_out_validation", -0.2))
    check = post(
        client,
        "validations",
        dict(
            actor="calibrator",
            operation_id="negative-transfer",
            calibration_id=fit["_id"],
            measurement_ids=[held["_id"]],
        ),
    )
    assert check["mae_after"] > check["mae_before"]
    different = synthetic(row, 4, "held_out_validation")
    different["measurement"]["setup"]["revision"] = "2"
    held = post(client, "measurements", different)
    post(
        client,
        "validations",
        dict(
            actor="calibrator",
            operation_id="wrong-setup",
            calibration_id=fit["_id"],
            measurement_ids=[held["_id"]],
        ),
        422,
    )


def test_portable_measurements_flag_missing_and_corrupted_artifacts(evidence, tmp_path):
    from davinci.product.measurement_contracts import EvidenceRestore

    client, row, _ = evidence
    record = post(client, "measurements", synthetic(row, "portable"))
    portable = post(client, "export", dict(ids=[record["_id"]], include_artifacts=False), 200)
    destination = Engine(
        tmp_path / "destination",
        runner=FixtureRunner(),
        provider=ForbiddenProvider,
        credentials=Settings(_env_file=None, openai_api_key="", mongodb_uri=""),
    )
    receipt = destination.measurements.restore(
        EvidenceRestore(actor="importer", operation_id="missing", bundle=portable)
    )
    imported = destination.measurements.get(receipt["items"][0])
    assert imported["evidence_issues"] and imported["link_status"] == "imported_unverified"
    portable = post(client, "export", dict(ids=[record["_id"]], include_artifacts=True), 200)
    portable["artifacts"][0]["data_base64"] = "eA=="  # checksum/size mismatch
    post(client, "import", dict(actor="importer", operation_id="corrupt-artifact", bundle=portable), 422)
