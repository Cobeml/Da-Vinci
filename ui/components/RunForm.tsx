"use client";
import { useEffect, useState } from "react";
import { parse, stringify } from "yaml";
import type { Config, Task } from "./types";
import s from "./workspace.module.css";
export default function RunForm({
  initial,
  onClose,
  onStarted,
}: {
  initial?: Config;
  onClose: () => void;
  onStarted: (id: string) => void;
}) {
  const [tasks, setTasks] = useState<Task[]>([]),
    [config, setConfig] = useState<Config | null>(initial || null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [yaml, setYaml] = useState("");
  useEffect(() => {
    fetch("/api/v1/tasks")
      .then((r) => r.json())
      .then((items: Task[]) => {
        setTasks(items);
        if (!initial) setConfig(parse(items[0].yaml));
      })
      .catch(() => setError("Cannot load task templates."));
  }, [initial]);
  const task = tasks.find((t) => t.id === config?.task.template),
    metrics = task?.metrics || {};
  const change = (value: Partial<Config>) =>
    setConfig((c) => (c ? { ...c, ...value } : c));
  async function loadYaml(text: string) {
    setYaml(text);
    setError("");
    try {
      const r = await fetch("/api/v1/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml: text }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      setConfig(d.config);
      if (task?.id === "custom")
        setTasks((ts) =>
          ts.map((t) => (t.id === "custom" ? { ...t, metrics: d.metrics } : t)),
        );
    } catch (e) {
      setError(String(e));
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      const r = await fetch("/api/v1/runs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ yaml: stringify(config) }),
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      onStarted(d.object_id);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  function download() {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(
      new Blob([stringify(config)], { type: "application/yaml" }),
    );
    a.download = "run.yaml";
    a.click();
    URL.revokeObjectURL(a.href);
  }
  return (
    <div className={s.overlay}>
      <section
        className={s.dialog}
        role="dialog"
        aria-modal="true"
        aria-label={initial ? "Continue from iteration" : "New object"}
      >
        <div className={s.sectionHeading}>
          <h2>{initial ? "Continue from iteration" : "New object"}</h2>
          <button
            type="button"
            className={s.quiet}
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {config && (
          <form onSubmit={submit}>
            {initial && (
              <p className={s.muted}>
                A new run will start from the selected geometry. Earlier results
                stay unchanged.
              </p>
            )}
            <div className={s.fields}>
              <label>
                Object name
                <input
                  required
                  maxLength={100}
                  value={config.object.name}
                  onChange={(e) =>
                    change({
                      object: { ...config.object, name: e.target.value },
                    })
                  }
                />
              </label>
              <label>
                Object ID
                <input
                  required
                  disabled={!!initial}
                  pattern="[a-z][a-z0-9-]{0,63}"
                  value={config.object.slug}
                  onChange={(e) =>
                    change({
                      object: { ...config.object, slug: e.target.value },
                    })
                  }
                />
              </label>
            </div>
            <label>
              Task template
              <select
                disabled={!!initial}
                value={config.task.template}
                onChange={(e) => {
                  const t = tasks.find((t) => t.id === e.target.value);
                  if (t) setConfig(parse(t.yaml));
                }}
              >
                {tasks.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
            {config.task.template === "custom" && (
              <label>
                Task directory (inside workspace)
                <input
                  required
                  value={config.task.path || "task"}
                  onChange={(e) =>
                    change({ task: { ...config.task, path: e.target.value } })
                  }
                />
              </label>
            )}
            <label>
              Task description
              <textarea
                required
                rows={3}
                value={config.task.description}
                onChange={(e) =>
                  change({
                    task: { ...config.task, description: e.target.value },
                  })
                }
              />
            </label>
            <div className={s.fields}>
              <label>
                Objective metric
                {Object.keys(metrics).length ? (
                  <select
                    value={config.objective.metric}
                    onChange={(e) =>
                      change({
                        objective: {
                          ...config.objective,
                          metric: e.target.value,
                        },
                      })
                    }
                  >
                    {Object.entries(metrics).map(([m, u]) => (
                      <option key={m} value={m}>
                        {m} ({u})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    value={config.objective.metric}
                    onChange={(e) =>
                      change({
                        objective: {
                          ...config.objective,
                          metric: e.target.value,
                        },
                      })
                    }
                  />
                )}
              </label>
              <label>
                Direction
                <select
                  value={config.objective.direction}
                  onChange={(e) =>
                    change({
                      objective: {
                        ...config.objective,
                        direction: e.target.value as "minimize" | "maximize",
                      },
                    })
                  }
                >
                  <option value="minimize">Minimize</option>
                  <option value="maximize">Maximize</option>
                </select>
              </label>
              <label>
                Target (optional)
                <input
                  type="number"
                  step="any"
                  value={config.objective.target ?? ""}
                  onChange={(e) =>
                    change({
                      objective: {
                        ...config.objective,
                        target:
                          e.target.value === "" ? null : Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
            </div>
            <fieldset>
              <legend>Additional constraints</legend>
              <p className={s.muted}>Fixed template checks always apply.</p>
              {config.constraints.map((c, i) => (
                <div className={s.constraint} key={i}>
                  <input
                    aria-label={`Constraint ${i + 1} metric`}
                    value={c.metric}
                    placeholder="Metric"
                    onChange={(e) =>
                      change({
                        constraints: config.constraints.map((x, j) =>
                          j === i
                            ? {
                                ...x,
                                metric: e.target.value,
                                unit: metrics[e.target.value] || x.unit,
                              }
                            : x,
                        ),
                      })
                    }
                  />
                  <select
                    aria-label={`Constraint ${i + 1} operator`}
                    value={c.operator}
                    onChange={(e) =>
                      change({
                        constraints: config.constraints.map((x, j) =>
                          j === i
                            ? { ...x, operator: e.target.value as "<=" | ">=" }
                            : x,
                        ),
                      })
                    }
                  >
                    <option>{"<="}</option>
                    <option>{">="}</option>
                  </select>
                  <input
                    aria-label={`Constraint ${i + 1} value`}
                    type="number"
                    step="any"
                    required
                    value={c.value}
                    onChange={(e) =>
                      change({
                        constraints: config.constraints.map((x, j) =>
                          j === i ? { ...x, value: Number(e.target.value) } : x,
                        ),
                      })
                    }
                  />
                  <input
                    aria-label={`Constraint ${i + 1} unit`}
                    value={c.unit}
                    onChange={(e) =>
                      change({
                        constraints: config.constraints.map((x, j) =>
                          j === i ? { ...x, unit: e.target.value } : x,
                        ),
                      })
                    }
                  />
                  <button
                    type="button"
                    className={s.quiet}
                    onClick={() =>
                      change({
                        constraints: config.constraints.filter(
                          (_, j) => j !== i,
                        ),
                      })
                    }
                    aria-label={`Remove constraint ${i + 1}`}
                  >
                    ×
                  </button>
                </div>
              ))}
              <button
                type="button"
                className={s.quiet}
                onClick={() =>
                  change({
                    constraints: [
                      ...config.constraints,
                      {
                        metric: "deflection_mm",
                        operator: "<=",
                        value: 0.5,
                        unit: "mm",
                      },
                    ],
                  })
                }
              >
                + Add constraint
              </button>
            </fieldset>
            <div className={s.fields}>
              <label>
                New iterations
                <input
                  type="number"
                  required
                  min={1}
                  max={50}
                  value={config.run.iterations}
                  onChange={(e) =>
                    change({
                      run: {
                        ...config.run,
                        iterations: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
              <label>
                API budget (USD)
                <input
                  type="number"
                  required
                  min={0.01}
                  max={1000}
                  step="any"
                  value={config.run.budget_usd}
                  onChange={(e) =>
                    change({
                      run: {
                        ...config.run,
                        budget_usd: Number(e.target.value),
                      },
                    })
                  }
                />
              </label>
              <label>
                Provider
                <select
                  value={config.run.mode}
                  onChange={(e) =>
                    change({
                      run: {
                        ...config.run,
                        mode: e.target.value as "live" | "replay",
                      },
                    })
                  }
                >
                  <option value="live">Live model</option>
                  <option value="replay">Deterministic replay</option>
                </select>
              </label>
            </div>
            <details>
              <summary>Load YAML configuration</summary>
              <label>
                YAML file
                <input
                  type="file"
                  accept=".yaml,.yml"
                  onChange={(e) => e.target.files?.[0]?.text().then(loadYaml)}
                />
              </label>
              <textarea
                aria-label="YAML configuration"
                rows={7}
                value={yaml}
                onChange={(e) => setYaml(e.target.value)}
              />
              <button
                type="button"
                className={s.quiet}
                onClick={() => loadYaml(yaml)}
              >
                Apply YAML
              </button>
            </details>
            {error && (
              <p role="alert" className={s.error}>
                {error}
              </p>
            )}
            <div className={s.actions}>
              <button type="button" className={s.quiet} onClick={download}>
                Download YAML
              </button>
              <button className={s.button} disabled={busy}>
                {busy ? "Starting…" : "Start run"}
              </button>
            </div>
          </form>
        )}
        {!config && <p>{error || "Loading templates…"}</p>}
      </section>
    </div>
  );
}
