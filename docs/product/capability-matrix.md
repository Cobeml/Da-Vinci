# Capability and evidence matrix

“Verified” below means the listed reproducible cases passed their specified checks, not general engineering certification. [Benchmark results](https://github.com/Cobeml/Da-Vinci/blob/master/docs/product/methodology-results.json) record native outputs. [Implementation record](implementation-methodology.md) lists execution commands and counts.

| Capability | Implemented | Verified evidence | Unavailable or limited |
|---|---|---|---|
| External, keyless lifecycle | Public CLI/HTTP; one localhost owner; strict schemas | `test_external`, `test_external_cli`, native benchmark and installed-wheel journey | No remote multi-user authorization |
| Built-in request to report | Requirements, references, freeze, iterations, final evidence, clarifications | Deterministic `test_managed`; native request/route checks; installed automatic journey | Autonomous model reliability not measured here; automatic recipe scope is narrow |
| Both-driver static solid evaluation | Optional Gmsh/CalculiX, STEP-derived mesh, semantic bindings, convergence | [Structural reference and bracket cases](structural-simulation.md), both-driver native benchmark | Linear isotropic small-deformation solids only; no fatigue/contact/nonlinear/dynamics certification |
| Geometry regression and bad evaluator detection | Frozen interfaces/limits, references and linked corrections | Deliberately shortened part and invalid evaluator rejected in native benchmark; lifecycle correction tests | References cannot prove every possible evaluator correct |
| Capability/resource handling | Explicit unsupported/invalid/numerical/resource states | Fatigue and over-capacity benchmark requests rejected before candidates; simulation resource tests | GPU presence does not establish test adequacy; no automatic cloud provisioning |
| Restart, cancellation, handoff | Persisted ownership and operation fencing, explicit resume | Lifecycle, managed, external and transfer tests | Uncertain paid calls require explicit resolution; no arbitrary process checkpointing |
| Final evidence and reproducibility | Artifact integrity, coverage, separate acceptance/targets | Twelve native modeled cases, repeated independent final evaluation, cross-driver metric comparison | Complete evidence can establish physical failure rather than acceptance |
| Cross-task memory | Scoped lexical/optional vectors; hypotheses; exact evidence lookup | Fixed-corpus held-out memory on/off benchmark; leakage/scope tests | False same-context lessons still retrieved; no design benefit demonstrated |
| Physical observations | Specimen/CAD/material/process/setup/uncertainty/source links | Synthetic software fixtures, unit conversion and integrity/partition checks | No real laboratory data, authenticity verification or specimen tracking hardware |
| Calibration | Versioned descriptive offset, separate held-out specimens | Synthetic improving and worsening hold-out comparisons | No predictive uncertainty model, blinded study, automatic solver correction or cross-suite transfer |
| Evidence export/import | Scoped records, checksums, bounded artifact bundles, origin preservation | Round-trip, corruption/missing artifact and trust-boundary tests | Imported claims are never locally reproduced evidence automatically |
| Tested tool learning | Isolated numeric/CAD helper versions, checks, pinning, rollback | [Tool-learning checks](tool-learning.md), existing native gate | No automatic replacement of installed trusted physics |
| Packaged local operation | UI/docs/schemas/agent instructions; optional native images | Fresh wheel outside checkout, no host Gmsh/CAD dependency | Optional Docker runtimes must be installed explicitly |
| Live-model comparison | Opt-in, fixed budgets/trials, independent contract/oracle checks | Local opt-in and relaxed-threshold rejection tests | No paid/live trials or autonomous-improvement claim in this phase |
