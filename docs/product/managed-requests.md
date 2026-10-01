# Managed engineering requests

The managed route accepts a description and configured generation credentials without a task directory, builder, baseline, or evaluator. The workspace service persists authoring stages, calls the existing provider, and uses the same lifecycle operations and physical jobs as an external coding agent. CLI commands return JSON and do not start a second execution owner.

**Current automatic verification scope:** the shipped `rectangular-beam-v1` recipe supports a rectangular prismatic cantilever, fixed length/width, and variable thickness under a static transverse tip force. It is an analytic mass/stress/deflection screen for a linear isotropic material. It is not a generic FEA, fatigue, joint, contact, dynamics, or certified uncertainty solver. Other requests receive clarification or an unavailable-capability explanation before candidate generation. Sensor/gripper/VTOL YAML examples and externally authored custom tests continue through their existing routes.

## Start from a request

From an installed checkout or wheel:

```bash
davinci init ./beam-workspace --driver managed
davinci --workspace ./beam-workspace setup
davinci --workspace ./beam-workspace service ensure
```

Configure `OPENAI_API_KEY` for the service and the model, pricing identity, accounting rates, output-token limit, and daily budget in `workspace.yaml` before starting it. The service reads its environment/workspace credentials at startup. Generation pricing is explicitly configured accounting, not a published price quote. SQLite/local artifacts remain the default. Embeddings are independent and disabled by default; enabling local hashing does not require a model key.

```bash
davinci --workspace ./beam-workspace managed request \
  --object beam --name 'Aluminium cantilever' --operation-id beam-request-1 \
  --budget-usd 10 --max-candidates 4 --search coordinate \
  --description 'Minimize mass of a rectangular prismatic aluminium cantilever: 40 mm long, 20 mm wide, thickness 2 to 8 mm, clamped root, transverse tip force 100 N. Use nominal E=70000 MPa and density=0.0027 g/mm3 for an analytic small-deflection screen. Hard limits: stress <=100 MPa and tip deflection <=0.5 mm. No fatigue, joints or dynamic loads.'
```

This resolves the already installed `da-vinci-cad:local` image to its immutable digest and returns the experiment immediately. It does not download or provision a solver. Record the returned `_id`:

```bash
davinci --workspace ./beam-workspace managed status EXPERIMENT_ID
davinci --workspace ./beam-workspace managed results EXPERIMENT_ID
davinci --workspace ./beam-workspace managed report EXPERIMENT_ID
```

`managed.status`, `managed.stage`, `pending_input`, `next_actions`, job records, and retained artifacts explain progress. The installed browser exposes this request workflow through **New object → Built-in agent**. Its object view shows pending questions, assumptions, tests, capabilities, iterations and the report. **Advanced YAML / custom task** preserves the v1 workflow.

If required engineering inputs are missing, the model returns focused questions. Their IDs, text, answers and subsequent requirements revision remain in the ledger. Put a question-ID-to-answer mapping in `answers.json` and submit it:

```bash
davinci --workspace ./beam-workspace managed answer EXPERIMENT_ID \
  --operation-id answer-1 --file answers.json
```

Ordinary stages proceed automatically. There is no approval prompt for each plan, fixture, proposal, or reflection. Inspect requirements and assumptions: local checks enforce units, declared inputs, recipe bounds, coverage and immutability; they do not prove that a language model interpreted an ambiguous request correctly.

## Stages and permissions

1. **Requirements/assumptions:** typed requirements and physical inputs with provenance, unresolved critical inputs, and recipe applicability. Model outputs cannot assert verified evidence.
2. **Experience retrieval:** scoped shared memory, with evidence status and applicability retained. Prior passes never certify the new task.
3. **Test plan:** the model composes a task-specific plan from the selected recipe. Local comparison rejects changes to its requirements, material/load inputs, fixed interfaces, limits, numerical accuracy or design bounds. This phase does not accept arbitrary unverified physical models.
4. **Setup/evaluator authoring:** reuse shipped evaluator code or author its task-specific implementation. Code is stored as evaluator resources and only executed in the isolated verification path. It is never imported into the service process.
5. **Capabilities:** probe the pinned runtime, physics/material support and resources before building any candidate. A discovered gap blocks the automatic run. External lifecycle operations can explicitly create an unvalidated draft; managed operation does not silently substitute a cheaper model or automatically approve a draft.
6. **Verification:** build trusted recipe fixtures, then run positive, negative, and invalid-geometry checks. Expected mass/stress/deflection come from a shipped closed-form reference, separate from the evaluator's matrix solution. Independent STEP inspection checks dimensions, solids, volume and root region. Thickness bounds must bracket passing and failing reference cases; otherwise clarify the bounds/limits rather than relaxing acceptance.
7. **Freeze:** shared coverage, capability and verification checks create an immutable suite. Test verification and freezing precede the first design candidate. Reference fixtures are labeled `reference_only`.
8. **Generate/evaluate:** model-generated CadQuery `build(parameters, interfaces)` sources and parameters follow the existing candidate bundle contract. A separate sandbox independently inspects exported STEP and runs the frozen tests. The recipe also compares every measured candidate result to its trusted algebraic oracle; candidate/evaluator flags cannot bypass the host's limits.
9. **Diagnose/reflect/revise:** model reasoning sees typed failures and measured margins. Reflections enter shared memory as hypotheses. Physical failure leads to design changes. Missing capability stops; numerical changes unsupported by the frozen recipe stop with an explanation. Invalid geometry can be repaired in the next proposal. Evaluator defects open a bounded linked correction, verify the new evaluator, and rerun the affected candidate sources and parameters; original suites/results stay unchanged.
10. **Final evaluation:** select the best candidate with complete evidence (feasible candidates first), resubmit its source/parameters, and execute the entire prescribed suite again. The report's final accepted IDs refer only to this rerun. An earlier successful search evaluation cannot cover missing final evidence.
11. **Experience recording:** capture committed physical observations with source/suite/runtime/artifact provenance. Model lessons retain hypothesis status.

Generated tests are currently task-specific instances/implementations of the trusted beam recipe. A new physics family needs a trusted reference recipe and adapter checks; this release cannot establish arbitrary model-authored evaluator truth. Additional diagnostic work can use a linked draft and the public fixture/verification operations, without injecting tests or weakening thresholds in the frozen parent suite. There is no automatic generic mesh/solver-tuning agent.

## Stopping, effort and restart

`SearchPolicy` is discoverable in the packaged JSON schemas. HTTP callers can configure all fields; the CLI exposes common settings.

- Candidate/minimum counts, stall patience, absolute objective improvement tolerance, and optional objective-target stopping are independent of hard acceptance criteria. The default optimization policy continues past a passing baseline. No target means no target-based early stop.
- `search: agent` requests conceptual/design revisions. `search: coordinate` uses bounded thickness bisection after a model-authored starting design for this monotone beam recipe only. Each point still builds and runs independent tests; the algebraic optimizer does not manufacture a passing score.
- All model authoring, malformed-structure repairs and diagnoses use the existing per-run/daily reservation ledger and persisted provider request IDs. Repair counts and correction depth are bounded. New linked evaluator corrections receive only remaining model budget and carry conservative solver reservations forward.
- `solver_compute_seconds` and `max_solver_jobs` cap physical effort. Runtime probes reserve 160 allocated CPU-seconds; each physical job reserves its configured upper bound plus 160 CPU-seconds for a possible uncached runtime probe (evaluation includes build and all tests). Failed/interrupted work retains its reservation. Existing container CPU/RAM/time/artifact bounds still apply. These are conservative allocations, not measured CPU utilization. Budget exhaustion blocks further work; it cannot create acceptance.
- Embedding accounting explicitly records zero API cost for the shipped disabled/local-hash adapters. There is no paid embedding implementation or implicit large-model download.
- Stage outputs are persisted before being applied. A restart reuses a completed provider checkpoint/output. Queued physical jobs remain queued; interrupted work requires explicit resume. Uncertain/received requests cannot be automatically repeated. Use a linked request after inspection, with an explicit new budget.

```bash
davinci --workspace ./beam-workspace managed cancel EXPERIMENT_ID --operation-id cancel-1
davinci --workspace ./beam-workspace managed resume EXPERIMENT_ID --operation-id resume-1
```

Resume does not erase failed/cancelled evidence. A cancelled candidate evaluation can enter diagnosis on resume; a cancelled final evaluation stays incomplete in the final report. Blocked capabilities or exhausted budgets require an explicit new/linked request, not an automatic spending increase.

## Existing-part edits

Supply `--existing-experiment` and `--existing-candidate` together. The service checks workspace/project scope and loads the existing source, parameters, plan and measured evidence for inspection. Original critical requirement IDs must remain covered. Automatic edits currently require an exactly compatible regression suite/material/interfaces before freeze; incompatible edits stop and require an externally verified linked plan. No inherited result becomes a new passing evaluation.

## Public contracts

| Operation | HTTP | Purpose |
| --- | --- | --- |
| Start | `POST /api/v2/managed-experiments` | `ManagedRequest`: description, object, actor/operation ID, pinned runtime, budget/policy; returns 202 |
| Recipes | `GET /api/v2/test-recipes` | Scope, limitations and input schema |
| Status | `GET /api/v2/experiments/{id}` | Durable stage, questions, revisions, next actions |
| Answer | `POST /api/v2/experiments/{id}/answers` | `Answers`: actor/revision/operation ID plus question mapping |
| Results/report | Existing `/results` and `/report` | Shared typed physical evidence and final checks |
| Cancel/resume | Existing `/cancel` and `/resume` | Shared owner/revision/idempotency controls |
| Artifacts/memory | Existing artifact and memory operations | Same provenance, checksums, scope and unverified-claim rules |

Stage outputs are `RequirementsOutput`, `TestPlanOutput`, `SetupOutput`, `Candidate`, and `DiagnosisOutput`; inputs use `StageInput`. `davinci external schemas` and `/api/v2/schemas` expose these even without credentials. The old manual `managed/{author,propose,reflect}` endpoints remain available for non-automatic v2 experiments, but cannot advance automatic requests. The workspace worker is their sole stage owner. External experiments never enter this loop.

Same opening operation and identical request reuse the experiment. A changed payload conflicts. Answers use revision checks and idempotency receipts. CLI envelopes and exit codes match the external route: success means the operation succeeded, not that an engineering design passed.

## Compatibility and limitations

No database migration, second engine, mandatory provider, remote scheduler, or hosted service is added. New automatic state is additive under `runs.managed`. Existing v1 tasks, v2 experiments and archived evidence remain unchanged. `Verification.expected_status` adds `invalid_setup` for negative geometry fixtures; pass/failure numeric references retain their previous contracts. Harness/recipe source identities are pinned in the suite, so a previously frozen suite affected by updated execution code needs a linked revision to run again; it is never retroactively revalidated.

Native integration uses actual CadQuery/OCP geometry and NumPy beam execution. It demonstrates the supported analytic screen and orchestration, not flight, manufacturing, laboratory, or generic FEA validation. The deterministic provider fixture is the default test path. A paid live smoke is separately opt-in, described in the implementation record.
