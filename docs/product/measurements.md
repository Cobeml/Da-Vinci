# Measurements and calibration

Physical observations are attributed evidence attached to a declared specimen, not simulation results. They cannot change a frozen evaluator, a trusted score or design acceptance. This release contains **no laboratory measurements**. All bundled observations are explicitly labeled `synthetic_fixture`.

## Public contract

Both drivers use the same localhost service and `davinci evidence` commands. `davinci external schemas` (GET `/api/v2/schemas`) includes `RecordMeasurement`, `MeasurementInput`, `CalibrationFit`, `CalibrationValidation`, `EvidenceExport` and `EvidenceRestore`. The JSON schemas are also installed in `davinci.product/resources/external/schemas.json`.

A measurement contains:

- A specimen ID; experiment, candidate and result IDs; actual STEP and source SHA-256 identities. The service checks the local CAD/result relationship and artifact integrity.
- Material name, source and batch, plus manufacturing/process method and source. These are attributed descriptions, not independently authenticated batch certificates.
- A versioned test setup, instruments, environmental conditions with dimensions/units where supplied, date with timezone, attribution and source.
- A quantity, dimensional unit, uncertainty magnitude, basis and interpretation. Expanded uncertainty also requires a coverage factor. No coverage probability or independence is invented.
- An immutable specimen partition: `calibration` or `held_out_validation`. `evidence_kind` distinguishes `physical_measurement` from `synthetic_fixture`.
- Optional prediction test/metric and an explicit comparability explanation; optional raw artifact references or bounded portable blobs.

Measurements currently link to v2 evaluated/exported CAD. A failed design may have complete usable predictions. Invalid/incomplete simulation evidence cannot supply a predicted comparison. Measurement-only records may omit the prediction link. Unbuilt specimens and historical v1 records need an explicit new v2 CAD evaluation; old evidence is never relabeled.

```bash
davinci service ensure
davinci evidence measure --file observation.json
davinci evidence inspect ATTRIBUTED_ID
davinci evidence list --limit 20
davinci evidence calibrate --file calibration.json
davinci evidence validate --file held-out.json
davinci evidence export --ids VALIDATION_ID --include-artifacts --output observations.json
davinci evidence import --file restore-command.json
```

`observation.json` follows `RecordMeasurement`: `{ "actor": "lab-importer", "operation_id": "observation-1", "measurement": {...}, "artifacts": [] }`. Supply actual attributed observations; do not use predicted values as laboratory data. The packaged `davinci.product.measurement_examples` module shows the complete payload **using synthetic values solely for software verification**.

`calibration.json` contains `actor`, `operation_id`, `name`, at least three `measurement_ids`, `applicability`, and optionally `predecessor_id`. `held-out.json` contains `actor`, `operation_id`, `calibration_id` and held-out `measurement_ids`. `restore-command.json` contains `actor`, `operation_id` and the exported JSON under `bundle`.

HTTP equivalents are POST `/api/v2/evidence/measurements`, `/calibrations`, `/validations`, `/export`, `/import`; GET `/api/v2/evidence` and `/api/v2/evidence/{id}`. List results provide `next_cursor`; use `after_id` on HTTP or `--cursor` on CLI. Mutations are idempotent by scoped actor/operation ID; different payloads under the same operation fail with conflict. Existing stable CLI JSON envelopes and exit codes apply.

## Comparison and validation boundaries

Prediction comparisons convert compatible dimensions into the prediction unit and retain observed-minus-predicted residuals. Observation uncertainty, simulation uncertainty and numerical error remain separate. A supplied comparability explanation is an attributed assertion, not proof that a physical test matches a simulated boundary condition.

The initial calibration is deliberately small: a descriptive additive offset, fitted to at least three distinct calibration specimens. All observations in a fit must share material/process, setup revision, evidence kind, uncertainty interpretation, metric, suite, evaluator and runtime identities. Held-out validation uses separate specimens with the same context. It reports MAE before/after and retains worsening outcomes. It does not supply a predictive uncertainty model, extrapolate to another geometry family or automatically correct a solver. A new fit is a new immutable record linked through `predecessor_id`.

A specimen cannot be reassigned between partitions or CAD/material/process identities. One observation per specimen is permitted in each fit/check. A correction uses `supersedes` while retaining specimen and partition; old observations and fits remain inspectable. Select corrected observations explicitly for a new fit. Users control specimen identity and can see held-out data: this is bookkeeping against accidental leakage, **not blinded experimental governance**. Repeatedly tuning against the same hold-out set invalidates a generalization claim.

Evidence exports preserve origin, record checksums and dependency closure. Artifact bundles are bounded to 12 MB; command bodies to 20 MB. Larger raw data stays in separately managed artifacts/references. Missing/corrupt imported artifacts are reported, not silently treated as evidence. Imports always remain `imported_unverified`; they cannot be fitted as locally reproduced observations. Explicitly submit a new attributed measurement against a local CAD revision to establish a local link. Checksums establish integrity, not authenticity. Searchable measurement notes remain unverified hypotheses; neither import nor calibration grants `measurement_supported` status automatically.

Storage is additive in SQLite documents or optional Atlas with local/GridFS artifacts; no migration or hosted service is required. No model key, embedding provider or model call is used. See [methodology evidence](methodology.md) for tests and negative synthetic calibration results.
