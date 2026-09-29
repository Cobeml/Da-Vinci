# Using the workspace

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
