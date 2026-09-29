# Configuration

`run.yaml` describes one run. Unknown fields, duplicate keys, invalid bounds, nonfinite numbers, and incorrect metric units are rejected before execution.

```yaml
version: 1
object:
  slug: inspection-mount
  name: Inspection sensor mount
task:
  template: sensor
  description: Reduce material while preserving mounting interfaces and stiffness.
objective:
  metric: mass_g
  direction: minimize
  target: 70
constraints:
  - metric: deflection_mm
    operator: "<="
    value: 0.5
    unit: mm
run:
  iterations: 6
  budget_usd: 10
  mode: live
```

- `object.slug` identifies the persistent object; use lowercase letters, numbers, and hyphens, starting with a letter. A different slug creates another object.
- `task.template`: `sensor`, `gripper`, `vtol`, or `custom`. Custom tasks also set `task.path` to a directory inside the workspace.
- `task.description`: qualitative engineering instructions for the agent.
- `objective`: one declared metric, `minimize` or `maximize`, and an optional target in that metric's declared units. The target guides proposals; it is not an automatic stop condition or a hard feasibility gate.
- `constraints`: additional hard limits using `<=` or `>=`. Units must match exactly. Fixed physical checks remain active regardless of user limits.
- `run.iterations`: 1–50 new proposals, plus one independently evaluated baseline.
- `run.budget_usd`: positive API accounting limit, maximum 1000. The workspace daily limit also applies.
- `run.mode`: `live` or explicitly labeled `replay`.
- `continuation.seed_candidate_id`: optional existing buildable candidate from the same object. The UI populates this automatically.

Run IDs and candidate IDs are local to the workspace database. Continuation YAML is portable within that workspace; importing it into another workspace without the referenced candidate is rejected.

## Templates

| Template | Typical objective | Other metrics | CAD runtime |
|---|---|---|---|
| Sensor | `mass_g`, minimize | `deflection_mm`, `stress_mpa`, `safety_factor`, `volume_cm3` | CAD image |
| Gripper | `mass_g`, minimize | `total_mass_g`, `deflection_mm`, `stress_mpa`, `buckling_factor`, `clearance_mm`, `travel_mm` | CAD image |
| VTOL | `range_km`, maximize | `max_speed_m_s`, `payload_capacity_kg`, `mass_kg`, `endurance_min`, `hover_power_w`, `static_margin`, `stall_speed_m_s`, `best_range_speed_m_s` | VTOL image |

Create complete examples with `davinci init DIRECTORY --template NAME`. The VTOL template retains at least 95% of the run baseline's speed and payload capacity. Its battery, payload, mission assumptions, and physical checks remain fixed. Changing physical assumptions requires a custom adapter and a new version, not merely changing the prompt.

## Workspace settings

```yaml
storage: local                 # or atlas
port: 8741
model: gpt-6-astra
pricing_model: gpt-6-astra
input_usd_per_million: 20
output_usd_per_million: 75
daily_budget_usd: 50
output_tokens: 6000
```

Model rates are configurable conservative accounting estimates, not a current vendor price quote. Verify them for your model and account. Changing `model` requires matching `pricing_model` and appropriate rates. Generation uses the Responses API; embeddings, when Atlas is enabled, use `text-embedding-3-small` with a separately recorded $0.02/million-token estimate. Cache discounts are not assumed.

API tokens and MongoDB URIs belong in environment variables (`OPENAI_API_KEY`, `MONGODB_URI`) or `.env`, never in YAML. Settings and exports do not expose these secrets. The app does not need the developer's repository `.env` when installed elsewhere.

Storage is explicit: the presence of `MONGODB_URI` alone does not enable Atlas. Local SQLite records, CAD artifacts, request checkpoints, and source Git snapshots live in `.davinci/`.
