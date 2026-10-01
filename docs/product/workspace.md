# Using the workspace

**New object** offers **Built-in agent**, **External agent**, and **Advanced YAML / custom task**. The first two use the same v2 lifecycle, object gallery, run selector, test-plan view and design cards. Advanced workflows retain the v1 UI below. Generation credentials are configured on the server, never in a browser input. A missing key disables managed creation without disabling the external route.

A managed request starts with a description. Answer focused engineering questions when they appear; ordinary authoring, verification, freezing, generation and evaluation proceed automatically. Inspect assumptions, fixed requirements, test coverage, acceptance criteria, fidelity and uncertainty requirements. Unavailable physics or runtime capabilities stop the experiment visibly. Automatic authoring is currently scoped to the rectangular cantilever recipe.

An external experiment opens as a draft without task files. Expand **External agent connection and commands** for the workspace path, localhost URL and copyable public CLI instructions. The status distinguishes waiting for the coding agent, queued simulation, and executing simulation. Both routes expose typed outcomes, numerical error and uncertainty, source/STEP/GLB, solver evidence and a final JSON report. A completed run is never labeled a validated design merely because execution stopped.

The model viewer uses GLB derived from the exported STEP in a separate trusted sandbox. Preview failure does not supply a physical result. Original STEP, builder logs and solver evidence remain downloadable. Historical runs without a preview remain inspectable; they are not rewritten to add one.

## V2 continuation and handoff

At an idle frozen checkpoint, select a candidate and **Start continuation**. This opens a linked experiment with the identical frozen suite, reference-verification provenance and source/parameters, but no inherited candidate results. The seed is reevaluated. The continuation focus guides design search; it does not change acceptance limits. Changed engineering tests require a linked plan revision instead.

**Hand off this experiment** changes the driver and owner on the existing experiment. Supply the new driver/owner and a reason. The service rejects queued/running work, atomically changes ownership, fences stale commands, and retains suite identity and history. No transfer is necessary to finish either route. Completed runs use continuation; pre-freeze drafts and uncertain/interrupted requests are not automatic handoff points. Resume or resolve the request first. Model and solver budgets cannot be reset by handing off.

The built-in agent may adopt a verified frozen custom suite with an inspectable builder. It does not certify new arbitrary physics: corrections to an adopted custom evaluator require externally verified reference work. Automatic new-task authoring retains its documented recipe limits.

## Advanced YAML / custom task (legacy v1)

The gallery contains objects, not individual runs. Each object card shows a model, the latest run's status, and its best passing result. Drag in the viewport to rotate; click the object title or **View iterations** to open it.

An object page contains:

- A run selector and current generation/evaluation phase.
- Completed iteration count and API accounting.
- The best passing model and an objective progress chart.
- Every design, including failures, with metrics and STEP downloads.
- Collapsible reflection, checks, source, and tested tool outputs.

Comparisons use the selected run's independently evaluated baseline. Failed designs may have diagnostic metrics, but they cannot become the best design. A chart bar does not mean a failed design is validated. If the baseline itself fails, the UI does not calculate a percentage improvement against it.

## Continue a design

Choose **Continue from best** or **Continue from here**. Edit the task, objective, target, constraints, iteration count, or budget. Starting creates a new linked run; it never overwrites its parent.

The seed is reevaluated under the new constraints. Compatible memories and tools remain available. A new task version isolates old tools and memory, and uses the new adapter's builder with the selected parameters. Incompatible parameters are rejected.

A failed design can seed another run if it produced a STEP artifact. A design that never built cannot. Select the previous run through its link or the run selector to compare histories without conflating different constraints.

## Stop and resume

**Stop run** stops the loop and cancels an active CAD container. An already submitted model request may finish and incur cost; its response is archived before execution pauses. No subsequent iteration starts.

One run executes at a time. After restarting the server, interrupted runs are paused. **Resume** continues at saved checkpoints. A request whose outcome is uncertain is never blindly retried; continue from a saved design in a new run instead.

YAML downloads contain resolved run settings, including seed references, but no credentials. STEP downloads contain geometry. Git snapshots and request/evaluation records remain in the workspace for inspection.
