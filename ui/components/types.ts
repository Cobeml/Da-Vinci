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
