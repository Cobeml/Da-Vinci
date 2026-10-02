"""Explicit synthetic observation fixture, usable through public HTTP only."""


def synthetic_comparison(client, row, operation="synthetic-evidence"):
    result = row["results"][-1]
    test = result["tests"][0]
    metric = "mass_g"
    prediction = test["metrics"][metric]["value"]
    ids = []
    for i, delta in enumerate((0.1, 0.2, 0.3, 0.2, -0.2)):
        body = dict(
            actor="synthetic-fixture",
            operation_id=f"{operation}-{i}",
            measurement=dict(
                specimen=dict(
                    specimen_id=f"{operation}-SYNTHETIC-{i}",
                    cad=dict(
                        experiment_id=row["_id"],
                        candidate_id=result["candidate_id"],
                        result_id=result["id"],
                        geometry_sha256=result["artifacts"]["model.step"].removeprefix("artifact-"),
                        source_sha256=result["source_artifact"].removeprefix("artifact-"),
                    ),
                    material={
                        "name": "Synthetic nominal material",
                        "source": "Software fixture only",
                        "batch": "synthetic",
                    },
                    process={"method": "synthetic", "source": "Software fixture only"},
                ),
                partition="calibration" if i < 3 else "held_out_validation",
                evidence_kind="synthetic_fixture",
                quantity_name="mass",
                quantity=dict(
                    value=prediction + delta,
                    unit="g",
                    dimension="mass",
                    uncertainty=0.01,
                    uncertainty_kind="interval_half_width",
                    uncertainty_basis="Synthetic interval for test logic only",
                ),
                setup=dict(
                    id="synthetic-balance",
                    revision="1",
                    description="Synthetic numerical balance, not an instrument",
                    instruments=["Software fixture"],
                    source="measurement_examples.py",
                ),
                measured_at="2026-01-01T12:00:00Z",
                attribution="Explicit synthetic fixture",
                source="No laboratory measurement; prediction plus predefined synthetic residual",
                prediction=dict(
                    test_id=test["test_id"],
                    metric=metric,
                    comparability_basis="Synthetic nominal mass fixture in the same units, constructed for software verification",
                ),
            ),
        )
        ids.append(client.request("POST", "/api/v2/evidence/measurements", body)["_id"])
    fit = client.request(
        "POST",
        "/api/v2/evidence/calibrations",
        dict(
            actor="synthetic-fixture",
            operation_id=operation + "-fit",
            name="synthetic-offset",
            measurement_ids=ids[:3],
            applicability="Synthetic software fixture only, not a real calibration",
        ),
    )
    validations = []
    for i in (3, 4):
        validations.append(
            client.request(
                "POST",
                "/api/v2/evidence/validations",
                dict(
                    actor="synthetic-fixture",
                    operation_id=f"{operation}-heldout-{i}",
                    calibration_id=fit["_id"],
                    measurement_ids=[ids[i]],
                ),
            )
        )
    portable = client.request(
        "POST", "/api/v2/evidence/export", dict(ids=[r["_id"] for r in validations], include_artifacts=True)
    )
    restored = client.request(
        "POST",
        "/api/v2/evidence/import",
        dict(actor="synthetic-fixture", operation_id=operation + "-restore", bundle=portable),
    )
    return dict(
        evidence_kind="synthetic_fixture",
        calibration=fit,
        validations=validations,
        restored=restored,
        claim="These values were constructed from predictions for software tests. They are not laboratory measurements or evidence of physical calibration benefit.",
    )
