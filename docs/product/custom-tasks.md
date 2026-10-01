# Custom engineering tasks

```bash
davinci init bracket-study --template custom
cd bracket-study
```

The starter is a simple cantilever plate with a separate analytic evaluator. Customize `task/` with your own coding agent or editor, then run `davinci validate run.yaml` and a baseline check before a paid campaign.

## External coding-agent route

Use `davinci init bracket-study --driver external --template custom` for keyless agent-driven work. This extends the custom-task workflow with a v2 plan/evaluator bundle, reference verification, immutable suite freeze, source/parameter submission and queued execution. The existing v1 files in `task/` remain available; the v2 example is in `external/`. See the [complete external-agent walkthrough](external-agents.md).

External agents use CLI/HTTP operations through the workspace service, never direct database writes. Their reflections remain unverified claims, and they cannot upload trusted scores. V2 uses the same `build(parameters, interfaces)` Assembly contract, with semantic interface definitions supplied as a list. Its independent evaluator is `evaluate(step_path, request)`, with frozen test inputs and no editable parameter claims. Existing v1 evaluators below are not silently upgraded; adapting one requires explicit v2 coverage and reference verification.

## Managed v1 contract

`task.json` declares:

- `name`, `baseline`, `specification`, and `image`.
- `parameters_schema`: JSON Schema used to validate agent proposals.
- `metrics`: a mapping from metric names to exact unit strings.
- Optional `files`: explicit Python, JSON, or text resources inside the task directory. Files are snapshotted; arbitrary workspace directories and secrets are not mounted.

`build.py` defines:

```python
def build(parameters, interfaces):
    # Return a CadQuery Assembly, using millimetres.
    return assembly
```

The agent can propose edits to this builder. `evaluate.py` defines the trusted contract:

```python
def evaluate(step_path, parameters, specification):
    return {
        "outcome": "passed",  # or failed
        "metrics": {"mass_g": {"value": measured_mass, "unit": "g"}},
        "violations": [],    # [{"code": "LIMIT", "message": "..."}]
        "fidelity": "your_physical_model",
        "limitations": "Assumptions and unsupported conditions.",
    }
```

The evaluator must independently check exported geometry against its supported physical model. A parameter-only calculation that ignores STEP geometry is insufficient. NaN, missing objective/constraint metrics, wrong units, and failed checks cannot produce a passing winner.

The product additionally checks STEP solid validity and exports a GLB preview. Both builder and evaluator run in separate network-isolated containers. The agent cannot change the frozen evaluator or its dependencies. Files and runtime image digest are captured at run creation; editing a task creates a new version for future runs.

A task image must provide Python, CadQuery, and the evaluator's dependencies, and run with the existing sandbox's unprivileged user and read-only filesystem. Place new solver dependencies in a separate Docker image rather than modifying the running host environment.

## Optional generated tools

Without tool fixtures, custom tasks use reflection and memory only. To enable the MVP's measured-objective helper, define `tool_contract` and include `tool_check.py` in `files`. The contract must use `run(arguments)` with `baseline`, `current`, and `direction`, matching the documented built-in objective-change utility. The trusted test script imports the generated tool and writes `/output/result.json` containing `{"passed": true, "checks": [...]}` only after its assertions pass. The same purity restrictions as built-in tools apply: math imports and numeric operations, no filesystem or dynamic execution.

This MVP intentionally supports a narrow tested utility contract. Arbitrary dynamic tool protocols and task-specific solver plugins require extending the Python adapter; they are not silently accepted through YAML.

## Prompt for a coding agent

> Read Da Vinci's custom-task interface and adapt the starter task for [engineering task]. Define the geometry parameters, fixed interfaces, objective, constraints, units, and baseline. Implement the CadQuery builder and an independent evaluator using [physical model or solver]. Add validation cases for known feasible and infeasible designs, document assumptions and unsupported conditions, and produce a runnable YAML configuration. Keep the evaluator outside the design agent's editable files. Run the adapter checks and a local baseline evaluation before requesting a paid optimization run. Preserve archived results; changes to the task or evaluator must create a new version.

Include load cases, materials, dimensions, manufacturing constraints, expected solver fidelity, and acceptance thresholds in the prompt. Ask the coding agent to identify unsupported physics explicitly rather than fabricating validation.


For new test-first custom tasks, declare a scoped simulation adapter and fixed semantic regions before freezing the plan. See [simulation adapters and evidence](simulation-adapters.md). Legacy custom evaluators remain supported with task-declared physics and unverified coverage; the plugin boundary does not establish general solver capability.


## Installed UI and driver adoption

Use **Advanced YAML / custom task** for the existing directory-based workflow, or create an **External agent** draft for v2 authoring. External and managed v2 runs share the gallery, coverage/limit display, measured iterations, artifacts and final report. Only explicitly frozen/verified tests can accept a design; a completed custom run is not automatically validated.

An external agent can hand a frozen suite with an inspectable reference/candidate builder to the built-in agent for proposal/reflection. This does not upgrade the evaluator's physics fidelity or allow changing thresholds. Arbitrary new custom evaluator verification remains the author's responsibility through the isolated reference path. See [ownership and continuation](workspace.md).
