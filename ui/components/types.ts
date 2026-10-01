export type Config = {
  version: number;
  object: { slug: string; name: string };
  task: { template: string; description: string; path?: string };
  objective: {
    metric: string;
    direction: "minimize" | "maximize";
    target?: number | null;
  };
  constraints: {
    metric: string;
    operator: "<=" | ">=";
    value: number;
    unit: string;
  }[];
  run: { iterations: number; budget_usd: number; mode: "live" | "replay" };
  continuation?: { seed_candidate_id: string } | null;
};
export type Evaluation = {
  outcome: string;
  metrics: Record<string, { value: number; unit: string; fidelity?: string }>;
  violations: { code: string; message: string }[];
  limitations?: string;
  fidelity?: string;
};
export type Design = {
  _id: string;
  run_id: string;
  iteration: number;
  title: string;
  change: string;
  parameters: Record<string, unknown>;
  source: string;
  artifacts: Record<string, string>;
  evaluation: Evaluation | null;
  reflection?: { lesson: string; next_focus: string } | null;
  tool_use?: { result: unknown } | null;
};
export type Run = {
  experiment?: Experiment;
  driver?: string;
  _id: string;
  status: string;
  phase: string;
  created_at: string;
  config: Config;
  completed_iterations: number;
  spent_usd: number;
  best_id: string | null;
  error?: string;
  parent_run_id?: string | null;
  seed_candidate_id?: string | null;
  task_version: string;
};
export type ObjectCard = {
  _id: string;
  name: string;
  template: string;
  run: Run | null;
  preview: Design | null;
  iteration_count: number;
  improvement_percent?: number | null;
  href?: string;
  previewUrl?: string;
};
export type Detail = {
  _id: string;
  name: string;
  template: string;
  runs: Run[];
  designs: Design[];
};
export type Task = {
  id: string;
  name: string;
  metrics: Record<string, string>;
  yaml: string;
};
export const artifactUrl = (id: string) =>
  `/api/v1/artifacts/${encodeURIComponent(id)}`;

export type Connection = {
  base_url: string;
  workspace: string;
  managed_available: boolean;
  external_available: boolean;
  storage: string;
  model: string;
};
export type TestResult = {
  test_id: string;
  status: string;
  reason: string;
  message: string;
  applicable: boolean;
  mesh_valid: boolean;
  metrics: Record<
    string,
    {
      value: number;
      unit: string;
      numerical_error: number;
      uncertainty: number;
    }
  >;
  metadata?: { fidelity?: string; stage?: string };
};
export type PhysicalResult = {
  id: string;
  candidate_id: string;
  tests: TestResult[];
  artifacts: Record<string, string>;
  evidence_complete: boolean;
  execution_completed: boolean;
  design_accepted: boolean;
  objective_target_attained: boolean | null;
  duration_seconds: number;
  manifest?: {
    entries: {
      name: string;
      artifact_id: string;
      sha256: string;
      kind: string;
    }[];
  };
  suite_id: string;
};
export type Experiment = {
  _id: string;
  revision: number;
  actor: string;
  driver: "external" | "managed";
  phase: string;
  status: string;
  mode: string;
  description: string;
  suite_id: string | null;
  draft_only: boolean;
  pending_input: string[];
  spent_usd: number;
  budget_usd: number;
  plan: {
    requirements: {
      id: string;
      description: string;
      resolved: boolean;
      critical: boolean;
    }[];
    assumptions: {
      description: string;
      source: string;
      applicability: string;
    }[];
    tests: {
      id: string;
      requirements: string[];
      required: boolean;
      applicability: string;
      metrics: Record<string, string>;
      criteria: {
        metric: string;
        operator: string;
        limit: number;
        unit: string;
      }[];
      accuracy: Record<
        string,
        { method: string; max_numerical_error: number; max_uncertainty: number }
      >;
      simulation?: { fidelity: string; stage: string };
    }[];
    objective?: {
      metric: string;
      direction: string;
      target: number | null;
    } | null;
  };
  coverage?: { complete: boolean; uncovered_critical: string[] };
  capabilities?: Capability[];
  results: PhysicalResult[];
  experiences: { lesson: string; support: string }[];
  candidates: {
    id: string;
    title: string;
    change: string;
    iteration: number;
    source_artifact: string;
    parameters: Record<string, unknown>;
  }[];
  managed?: {
    stage: string;
    status: string;
    questions?: Record<string, string>;
    error?: string;
    stop_reason?: string;
    capability_report?: Capability[];
    correction_id?: string;
    experience?: {
      id?: string;
      claim?: string;
      lesson?: string;
      support?: string;
      applicability?: unknown;
    }[];
  };
  report?: {
    accepted_candidate_ids: string[];
    managed?: { final_evidence_complete: boolean };
    validation_gaps: string[];
  } | null;
  report_artifact?: string;
  parent_experiment_id?: string;
  continuation?: { experiment_id: string; candidate_id: string; focus: string };
  handoffs?: {
    from_driver: string;
    to_driver: string;
    from_actor: string;
    to_actor: string;
    reason: string;
  }[];
  job?: { status: string; kind?: string } | null;
  next_actions: string[];
};
export type Capability = {
  test_id: string;
  status: string;
  reason: string;
  simulation?: { adapter?: { limitations: string[] } };
};
