"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import Gallery from "./Gallery";
import RunForm from "./RunForm";
import {
  artifactUrl,
  type Config,
  type Design,
  type Detail,
  type ObjectCard,
} from "./types";
import s from "./workspace.module.css";
const Model = dynamic(() => import("./ModelViewer"), { ssr: false });
const number = (v: number) =>
  Number.isFinite(v)
    ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : "—";
export default function Workspace({
  objectPage = false,
}: {
  objectPage?: boolean;
}) {
  const [objects, setObjects] = useState<ObjectCard[]>([]),
    [detail, setDetail] = useState<Detail | null>(null),
    [id, setId] = useState(""),
    [runId, setRunId] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [form, setForm] = useState<Config | true | null>(null);
  useEffect(() => {
    if (objectPage)
      setId(new URLSearchParams(window.location.search).get("id") || "");
  }, [objectPage]);
  const refresh = useCallback(async () => {
    if (objectPage && !id) return;
    try {
      const r = await fetch(
        objectPage
          ? `/api/v1/objects/${encodeURIComponent(id)}`
          : "/api/v1/objects",
      );
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      if (objectPage) setDetail(d);
      else setObjects(d);
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }, [id, objectPage]);
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  }, [refresh]);
  const run = detail?.runs.find((r) => r._id === runId) || detail?.runs[0],
    active = run?.status === "running";
  useEffect(() => {
    if (!run?._id) return;
    const source = new EventSource(`/api/v1/runs/${run._id}/events`);
    source.onmessage = () => refresh();
    return () => source.close();
  }, [run?._id, refresh]);
  const designs =
    detail?.designs
      .filter((d) => d.run_id === run?._id)
      .sort((a, b) => a.iteration - b.iteration) || [];
  const best = designs.find((d) => d._id === run?.best_id),
    base = designs.find((d) => d.iteration === 0),
    metric = run?.config.objective.metric || "",
    bestValue = best?.evaluation?.metrics[metric]?.value,
    baseValue = base?.evaluation?.metrics[metric]?.value;
  const comparable =
    base?.evaluation?.outcome === "passed" &&
    bestValue !== undefined &&
    baseValue !== undefined &&
    baseValue !== 0;
  const gain = comparable
    ? ((bestValue! - baseValue!) / Math.abs(baseValue!)) *
      100 *
      (run?.config.objective.direction === "minimize" ? -1 : 1)
    : null;
  const maximum = Math.max(
    1,
    ...designs.map((d) => Math.abs(d.evaluation?.metrics[metric]?.value || 0)),
  );
  function continueFrom(d: Design) {
    if (!run) return;
    setForm({
      ...structuredClone(run.config),
      continuation: { seed_candidate_id: d._id },
    });
  }
  async function action(name: string) {
    if (!run) return;
    try {
      const r = await fetch(`/api/v1/runs/${run._id}/${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const d = await r.json();
      if (!r.ok) throw Error(d.detail);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <main className={s.page}>
      <nav className={s.nav}>
        <a href="/" className={s.brand}>
          Da Vinci<span>CAD workspace</span>
        </a>
        <a href="/docs/">Documentation ↗</a>
      </nav>
      {!objectPage ? (
        <>
          <header className={s.header}>
            <div>
              <span className={s.eyebrow}>LOCAL WORKSPACE</span>
              <h1>Objects</h1>
              <p>Design, evaluate, and continue from measured results.</p>
            </div>
            <button className={s.button} onClick={() => setForm(true)}>
              + New object
            </button>
          </header>
          {!loading && !objects.length && (
            <section className={s.empty}>
              <span className={s.eyebrow}>NO OBJECTS YET</span>
              <h2>Start with a task.</h2>
              <p>
                Choose a template or load your run YAML.
                <br />
                Each object keeps its designs, metrics, and run history.
              </p>
              <button className={s.button} onClick={() => setForm(true)}>
                Create an object
              </button>
              <code>davinci run run.yaml</code>
            </section>
          )}
          <Gallery objects={objects} />
        </>
      ) : (
        <>
          <a className={s.back} href="/">
            ← All objects
          </a>
          {detail && run && (
            <>
              <header className={s.header}>
                <div>
                  <span className={s.eyebrow}>
                    {detail.template} ·{" "}
                    {run.config.run.mode === "replay"
                      ? "DETERMINISTIC REPLAY"
                      : "LIVE MODEL"}
                  </span>
                  <h1>{detail.name}</h1>
                  <p>{run.config.task.description}</p>
                </div>
                <div className={s.controls}>
                  <label>
                    Run
                    <select
                      aria-label="Run"
                      value={run._id}
                      onChange={(e) => setRunId(e.target.value)}
                    >
                      {detail.runs.map((r, i) => (
                        <option key={r._id} value={r._id}>
                          {new Date(r.created_at).toLocaleString()} · {r.status}
                          {i === 0 ? " · latest" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {best && (
                    <button
                      className={s.button}
                      disabled={active}
                      onClick={() => continueFrom(best)}
                    >
                      Continue from best →
                    </button>
                  )}
                </div>
              </header>
              <section className={s.status} aria-label="Run progress">
                <div>
                  <span className={s.dot} data-active={active} />
                  <strong>{run.status}</strong>
                  <span>{run.phase.replaceAll("_", " ")}</span>
                </div>
                <span>
                  {run.completed_iterations} / {run.config.run.iterations} new
                  iterations
                </span>
                <span>
                  ${run.spent_usd.toFixed(3)} / ${run.config.run.budget_usd} API
                  accounting
                </span>
                <div className={s.actions}>
                  {active ? (
                    <button className={s.quiet} onClick={() => action("stop")}>
                      Stop run
                    </button>
                  ) : ["paused", "stopped"].includes(run.status) ? (
                    <button
                      className={s.quiet}
                      onClick={() => action("resume")}
                    >
                      Resume
                    </button>
                  ) : null}
                  <a href={`/api/v1/runs/${run._id}/yaml`}>YAML ↓</a>
                </div>
              </section>
              {run.error && <p className={s.error}>{run.error}</p>}
              {run.parent_run_id && (
                <p className={s.muted}>
                  Continued from{" "}
                  <button
                    className={s.inlineButton}
                    onClick={() => setRunId(run.parent_run_id!)}
                  >
                    a previous run
                  </button>
                  . Seed reevaluated under this run’s constraints.
                </p>
              )}
              <section className={s.overview}>
                <div className={s.hero}>
                  <Model
                    url={
                      (best || designs.find((d) => d.artifacts["model.glb"]))
                        ?.artifacts["model.glb"]
                        ? artifactUrl(
                            (best ||
                              designs.find((d) => d.artifacts["model.glb"]))!
                              .artifacts["model.glb"],
                          )
                        : undefined
                    }
                  />
                </div>
                <div className={s.progress}>
                  <span className={s.eyebrow}>
                    BEST PASSING {metric.replaceAll("_", " ")}
                  </span>
                  <div className={s.bigMetric}>
                    {bestValue !== undefined ? number(bestValue) : "—"}{" "}
                    <small>{best?.evaluation?.metrics[metric]?.unit}</small>
                  </div>
                  {gain !== null ? (
                    <p className={s.gain}>
                      {number(gain)}% improvement from baseline
                    </p>
                  ) : (
                    <p className={s.muted}>
                      No comparable passing baseline yet.
                    </p>
                  )}
                  <div className={s.chart} aria-label="Iteration progress">
                    {designs.map((d) => {
                      const value = d.evaluation?.metrics[metric]?.value;
                      return (
                        <a
                          key={d._id}
                          href={`#${d._id}`}
                          className={
                            d.evaluation?.outcome === "passed"
                              ? s.chartPoint
                              : s.failedPoint
                          }
                        >
                          <span>
                            {value === undefined ? "—" : number(value)}
                          </span>
                          <div
                            style={{
                              height: `${value === undefined ? 3 : Math.max(3, (Math.abs(value) / maximum) * 72)}px`,
                            }}
                          />
                          <small>
                            {d.iteration === 0
                              ? "Base"
                              : String(d.iteration).padStart(2, "0")}
                          </small>
                        </a>
                      );
                    })}
                  </div>
                  <p className={s.muted}>
                    Engineering estimates. Failed checks are excluded from the
                    best design.
                  </p>
                  <details>
                    <summary>Task and evaluation</summary>
                    <p>
                      Objective: {run.config.objective.direction} {metric}
                      {run.config.objective.target != null
                        ? ` · target ${run.config.objective.target}`
                        : ""}
                      .
                    </p>
                    {run.config.constraints.map((c, i) => (
                      <p key={i}>
                        {c.metric} {c.operator} {c.value} {c.unit}
                      </p>
                    ))}
                    <p>
                      {best?.evaluation?.limitations ||
                        base?.evaluation?.limitations ||
                        "Independent task evaluation. View iteration details for checks."}
                    </p>
                    <p>
                      Task version: <code>{run.task_version.slice(0, 16)}</code>
                    </p>
                  </details>
                </div>
              </section>
              <div className={s.sectionHeading}>
                <h2>Design iterations</h2>
                <span>{designs.length} designs · baseline included</span>
              </div>
              <section className={s.grid} aria-label="Design iterations">
                {designs.map((d) => (
                  <article
                    className={`${s.card} ${d._id === run.best_id ? s.bestCard : ""}`}
                    id={d._id}
                    key={d._id}
                    data-testid="iteration-card"
                  >
                    <div className={s.cardHeading}>
                      <span className={s.eyebrow}>
                        {d.iteration === 0
                          ? "BASELINE"
                          : String(d.iteration).padStart(2, "0")}
                      </span>
                      <span
                        className={
                          d.evaluation?.outcome === "failed"
                            ? s.failed
                            : s.badge
                        }
                      >
                        {d._id === run.best_id
                          ? "Best passing"
                          : d.evaluation?.outcome || "Evaluating"}
                      </span>
                    </div>
                    <Model
                      url={
                        d.artifacts["model.glb"]
                          ? artifactUrl(d.artifacts["model.glb"])
                          : undefined
                      }
                    />
                    <div className={s.cardBody}>
                      <h2>{d.title}</h2>
                      <p>{d.change}</p>
                      <dl className={s.metrics}>
                        {Object.entries(d.evaluation?.metrics || {}).map(
                          ([k, m]) => (
                            <div key={k}>
                              <dt>{k.replaceAll("_", " ")}</dt>
                              <dd>
                                {number(m.value)} <small>{m.unit}</small>
                              </dd>
                            </div>
                          ),
                        )}
                      </dl>
                      {d.evaluation?.violations.map((v, i) => (
                        <p key={i} className={s.error}>
                          {v.code.replaceAll("_", " ")}: {v.message}
                        </p>
                      ))}
                      <details>
                        <summary>Reflection, checks, and source</summary>
                        <p>{d.reflection?.lesson || "Reflection pending."}</p>
                        <p>{d.reflection?.next_focus}</p>
                        <p>{d.evaluation?.limitations}</p>
                        {d.tool_use && (
                          <p>
                            Tested tool output:{" "}
                            <code>{JSON.stringify(d.tool_use.result)}</code>
                          </p>
                        )}
                        <pre>{JSON.stringify(d.parameters, null, 2)}</pre>
                        <pre>{d.source}</pre>
                      </details>
                      <div className={s.cardFooter}>
                        {d.artifacts["model.step"] && (
                          <a
                            href={artifactUrl(d.artifacts["model.step"])}
                            download
                          >
                            STEP ↓
                          </a>
                        )}
                        <button
                          className={s.quiet}
                          disabled={active || !d.artifacts["model.step"]}
                          onClick={() => continueFrom(d)}
                        >
                          Continue from here →
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </section>
            </>
          )}
        </>
      )}
      {loading && <p className={s.muted}>Loading workspace…</p>}
      {error && (
        <p role="alert" className={s.error}>
          {error}
        </p>
      )}
      <footer className={s.footer}>
        <span>Da Vinci · Recursive improvement CAD harness</span>
        <span>Local workspace · immutable run history</span>
      </footer>
      {form && (
        <RunForm
          initial={form === true ? undefined : form}
          onClose={() => setForm(null)}
          onStarted={(objectId) => {
            setForm(null);
            window.location.href = `/object/?id=${encodeURIComponent(objectId)}`;
          }}
        />
      )}
    </main>
  );
}
