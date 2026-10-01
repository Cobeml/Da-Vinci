"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import ExternalConnection from "./ExternalConnection";
import {
  artifactUrl,
  type Capability,
  type Experiment,
  type PhysicalResult,
} from "./types";
import s from "./workspace.module.css";
const Model = dynamic(() => import("./ModelViewer"), { ssr: false });
const format = (n: number) =>
  n.toLocaleString(undefined, { maximumSignificantDigits: 6 });
function label(result: PhysicalResult | undefined, draft: boolean) {
  if (draft) return "Draft · unvalidated";
  if (!result) return "Not evaluated";
  if (result.design_accepted && result.evidence_complete)
    return "Accepted under stated tests";
  const statuses = result.tests.map((t) => t.status);
  if (statuses.includes("invalid_setup")) return "Invalid setup";
  if (statuses.includes("numerical_failure")) return "Numerical failure";
  if (statuses.includes("unsupported_capability"))
    return "Unsupported capability";
  if (!result.evidence_complete) return "Incomplete evidence";
  if (statuses.includes("physical_failure")) return "Physical failure";
  return "Not accepted";
}
function progress(e: Experiment) {
  if (["cancelled", "interrupted"].includes(e.phase))
    return "Execution stopped";
  if (e.phase === "queued") return "Simulation queued";
  if (["evaluating", "verifying"].includes(e.phase))
    return e.job?.kind ? "Executing simulation" : "Built-in agent working";
  if (e.phase === "awaiting_input") return "Engineering information needed";
  if (e.phase === "completed") return "Execution completed";
  if (e.driver === "external") return "Waiting on external agent";
  if (e.managed?.status === "blocked")
    return "Execution stopped · inspect limits";
  return "Built-in agent working";
}
export default function ExperimentPanel({
  experiment: e,
  refresh,
  onContinued,
}: {
  experiment: Experiment;
  refresh: () => void;
  onContinued: (id: string) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [answers, setAnswers] = useState<Record<string, string>>({}),
    [caps, setCaps] = useState<Capability[]>();
  const [seed, setSeed] = useState(""),
    [driver, setDriver] = useState(e.driver),
    [actor, setActor] = useState("coding-agent");
  const [reason, setReason] = useState(""),
    [budget, setBudget] = useState(10),
    [iterations, setIterations] = useState(4);
  useEffect(() => {
    setCaps(undefined);
    setAnswers({});
    setSeed("");
    setDriver(e.driver);
    setError("");
  }, [e._id]);
  async function mutate(action: string, payload: Record<string, unknown> = {}) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(`/api/v2/experiments/${e._id}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          actor: e.actor,
          revision: e.revision,
          operation_id: crypto.randomUUID(),
          ...payload,
        }),
      });
      const data = await r.json();
      if (!r.ok)
        throw Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail),
        );
      if (action === "continue") onContinued(data._id);
      else refresh();
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }
  const capabilities =
    caps || e.capabilities || e.managed?.capability_report || [];
  const questions = e.managed?.questions || {};
  const active = ["queued", "evaluating", "verifying"].includes(e.phase);
  const idle = [
    "frozen",
    "candidate_submitted",
    "evaluated",
    "reflected",
    "completed",
  ].includes(e.phase);
  const latest = e.results.at(-1),
    preview = [...e.results].reverse().find((r) => r.artifacts["model.glb"]);
  const covered = new Set(
    e.plan.tests.filter((t) => t.required).flatMap((t) => t.requirements),
  );
  return (
    <div data-testid="experiment-panel">
      <section className={s.status} aria-label="Run progress">
        <div>
          <strong>{progress(e)}</strong>
          <span>
            {e.driver === "external" ? "External agent" : "Built-in agent"} ·{" "}
            {e.driver === "managed"
              ? e.managed?.stage?.replaceAll("_", " ") || e.phase
              : e.phase.replaceAll("_", " ")}
          </span>
        </div>
        <span>
          ${e.spent_usd.toFixed(3)} / ${e.budget_usd} API accounting
        </span>
        {!["completed", "cancelled", "interrupted"].includes(e.phase) && (
          <button
            className={s.quiet}
            disabled={busy}
            onClick={() => mutate("cancel")}
          >
            Stop experiment
          </button>
        )}
        {["cancelled", "interrupted"].includes(e.phase) && (
          <button
            className={s.quiet}
            disabled={busy}
            onClick={() => mutate("resume")}
          >
            Resume experiment
          </button>
        )}
      </section>
      {error && (
        <p role="alert" className={s.error}>
          {error}
        </p>
      )}
      {(e.managed?.error || e.managed?.stop_reason) && (
        <p className={s.error}>
          {e.managed.error || e.managed.stop_reason?.replaceAll("_", " ")}
        </p>
      )}
      {e.parent_experiment_id && (
        <p className={s.muted}>
          Linked experiment: <code>{e.parent_experiment_id}</code>.{" "}
          {e.continuation
            ? "Same frozen suite; seed requires fresh evidence."
            : "No prior passing score is inherited."}
        </p>
      )}
      {e.phase === "awaiting_input" && (
        <section className={s.panel} aria-label="Clarification">
          <h2>Engineering information needed</h2>
          {Object.keys(questions).length ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                mutate("answers", { answers });
              }}
            >
              {Object.entries(questions).map(([id, question]) => (
                <label key={id}>
                  {question}
                  <textarea
                    required
                    maxLength={4000}
                    value={answers[id] || ""}
                    onChange={(event) =>
                      setAnswers({ ...answers, [id]: event.target.value })
                    }
                  />
                </label>
              ))}
              <button className={s.button} disabled={busy}>
                Submit engineering answers
              </button>
            </form>
          ) : (
            <ul>
              {e.pending_input.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          )}
        </section>
      )}
      {e.driver === "external" && <ExternalConnection experimentId={e._id} />}
      <section className={s.overview}>
        <div className={s.hero}>
          <Model
            url={
              preview ? artifactUrl(preview.artifacts["model.glb"]) : undefined
            }
          />
        </div>
        <div className={s.progress}>
          <h2>{label(latest, e.draft_only)}</h2>
          <p>
            {latest?.evidence_complete
              ? "Required evidence complete"
              : "Required evidence incomplete"}
          </p>
          <p>
            Objective target:{" "}
            {latest?.objective_target_attained == null
              ? "Not specified or not measured"
              : latest.objective_target_attained
                ? "Attained"
                : "Not attained"}
            . This is separate from required acceptance.
          </p>
          {e.report && (
            <section aria-label="Final report">
              <h3>Final report</h3>
              <p>
                {e.report.accepted_candidate_ids.length
                  ? `${e.report.accepted_candidate_ids.length} design(s) accepted under the stated tests.`
                  : "No design accepted in the final report."}
              </p>
              {e.report.managed && (
                <p>
                  Final evidence:{" "}
                  {e.report.managed.final_evidence_complete
                    ? "complete"
                    : "incomplete"}
                </p>
              )}
              <a
                href={`/api/v2/experiments/${e._id}/report`}
                target="_blank"
                rel="noreferrer"
              >
                Export report JSON ↗
              </a>
              {e.report_artifact && (
                <>
                  {" "}
                  ·{" "}
                  <a href={artifactUrl(e.report_artifact)}>Report artifact ↓</a>
                </>
              )}
            </section>
          )}
          <p className={s.muted}>
            Completion is an execution state, not physical validation.
            Acceptance applies only to the declared tests, fidelity and
            uncertainty limits.
          </p>
        </div>
      </section>
      <section className={s.panel} aria-label="Test plan">
        <h2>Requirements and test plan</h2>
        <p>
          {e.suite_id ? "Frozen suite" : "Draft plan"}:{" "}
          <code>
            {e.suite_id || "Not frozen — candidate generation is not allowed"}
          </code>
        </p>
        <p>
          Critical coverage:{" "}
          {e.plan.requirements.length &&
          e.plan.requirements
            .filter((r) => r.critical)
            .every((r) => covered.has(r.id))
            ? "complete"
            : "incomplete"}
        </p>
        <ul>
          {e.plan.requirements.map((r) => (
            <li key={r.id}>
              <strong>{r.id}</strong>: {r.description} ·{" "}
              {r.resolved ? "resolved" : "needs input"} ·{" "}
              {covered.has(r.id) ? "required test declared" : "not covered"}
            </li>
          ))}
        </ul>
        <details>
          <summary>Assumptions, material, loads and full plan</summary>
          {e.plan.assumptions.map((a, i) => (
            <p key={i}>
              {a.description} · {a.applicability} · Source: {a.source}
            </p>
          ))}
          <pre>{JSON.stringify(e.plan, null, 2)}</pre>
        </details>
        {e.plan.tests.map((t) => (
          <details key={t.id}>
            <summary>
              {t.id} · {t.required ? "Required" : "Diagnostic"} ·{" "}
              {t.simulation?.fidelity || "Declared legacy fidelity"}
            </summary>
            <p>{t.applicability}</p>
            <ul>
              {t.criteria.map((c, i) => (
                <li key={i}>
                  {c.metric} {c.operator} {c.limit} {c.unit}
                </li>
              ))}
            </ul>
            <p>
              Prescribed stage: {t.simulation?.stage || "declared test"}.
              Required accuracy and uncertainty:
            </p>
            <pre>{JSON.stringify(t.accuracy, null, 2)}</pre>
          </details>
        ))}
      </section>
      <section className={s.panel} aria-label="Capabilities">
        <h2>Simulation capabilities</h2>
        {!capabilities.length && (
          <p>Capabilities have not been checked for this plan.</p>
        )}
        {capabilities.map((c) => (
          <div key={c.test_id}>
            <strong>
              {c.test_id}: {c.status}
            </strong>
            <p>{c.reason}</p>
            <ul>
              {c.simulation?.adapter?.limitations.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        ))}
        {e.driver === "external" && e.plan.tests.length > 0 && (
          <button
            className={s.quiet}
            disabled={active || busy}
            onClick={async () => {
              setBusy(true);
              try {
                const r = await fetch(
                  `/api/v2/experiments/${e._id}/capabilities`,
                );
                const d = await r.json();
                if (!r.ok) throw Error(d.detail);
                setCaps(d);
              } catch (err) {
                setError(String(err));
              } finally {
                setBusy(false);
              }
            }}
          >
            Check configured capabilities
          </button>
        )}
      </section>
      <details className={s.panel}>
        <summary>Retrieved experience and reflections</summary>
        <p>
          Lessons are hypotheses unless backed by linked evidence. No passing
          score transfers between tasks.
        </p>
        {(e.managed?.experience || []).map((x, i) => (
          <div key={i}>
            <p>
              {x.claim || x.lesson || "Retrieved experience"} ·{" "}
              {x.support || "hypothesis"}
            </p>
            {x.id && (
              <a href={`/api/v2/memory/records/${encodeURIComponent(x.id)}`}>
                Inspect source evidence
              </a>
            )}
            <pre>{JSON.stringify(x.applicability, null, 2)}</pre>
          </div>
        ))}
        {e.experiences.map((x, i) => (
          <p key={i}>
            {x.lesson} · {x.support} (not independent verification)
          </p>
        ))}
        <a
          href={`/api/v2/experience?q=${encodeURIComponent(e.description)}&experiment_id=${e._id}`}
        >
          Search relevant scoped experience ↗
        </a>
      </details>
      <div className={s.sectionHeading}>
        <h2>Design iterations</h2>
        <span>{e.candidates.length} designs</span>
      </div>
      <section className={s.grid} aria-label="Design iterations">
        {e.candidates.map((c) => {
          const result = e.results
            .filter((r) => r.candidate_id === c.id)
            .at(-1);
          return (
            <article className={s.card} key={c.id} data-testid="iteration-card">
              <div className={s.cardHeading}>
                <span>{String(c.iteration + 1).padStart(2, "0")}</span>
                <span className={result?.design_accepted ? s.badge : s.failed}>
                  {label(result, e.draft_only)}
                </span>
              </div>
              <Model
                url={
                  result?.artifacts["model.glb"]
                    ? artifactUrl(result.artifacts["model.glb"])
                    : undefined
                }
              />
              <div className={s.cardBody}>
                <h3>{c.title}</h3>
                <p>{c.change}</p>
                <p>
                  Evidence:{" "}
                  {result?.evidence_complete ? "complete" : "incomplete"} ·
                  Target:{" "}
                  {result?.objective_target_attained == null
                    ? "not assessed"
                    : result.objective_target_attained
                      ? "attained"
                      : "not attained"}
                </p>
                {result?.tests.map((t) => (
                  <div key={t.test_id}>
                    <strong>
                      {t.test_id}: {t.status.replaceAll("_", " ")}
                    </strong>
                    <p>
                      {t.reason} {t.message} ·{" "}
                      {t.metadata?.fidelity || "declared fidelity"}
                    </p>
                    <dl className={s.metrics}>
                      {Object.entries(t.metrics).map(([metric, m]) => (
                        <div key={metric}>
                          <dt>{metric}</dt>
                          <dd>
                            {format(m.value)} {m.unit}
                          </dd>
                          <small>
                            Numerical ±{format(m.numerical_error)} · uncertainty
                            ±{format(m.uncertainty)} {m.unit}
                          </small>
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
                <details>
                  <summary>Artifacts, tests and provenance</summary>
                  <a href={artifactUrl(c.source_artifact)}>CAD source ↓</a>
                  <pre>{JSON.stringify(c.parameters, null, 2)}</pre>
                  <ul>
                    {Object.entries(result?.artifacts || {}).map(
                      ([name, id]) => (
                        <li key={name}>
                          <a href={artifactUrl(id)}>{name} ↓</a>
                        </li>
                      ),
                    )}
                  </ul>
                  <pre>{JSON.stringify(result?.manifest, null, 2)}</pre>
                </details>
                <div className={s.cardFooter}>
                  {result?.artifacts["model.step"] && (
                    <a href={artifactUrl(result.artifacts["model.step"])}>
                      STEP ↓
                    </a>
                  )}
                  <button
                    className={s.quiet}
                    disabled={!idle || busy}
                    onClick={() => {
                      setSeed(c.id);
                      document
                        .getElementById("transfer-controls")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    Continue from this design
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </section>
      <section className={s.panel} id="transfer-controls">
        <h2>Continue or hand off</h2>
        <p>
          Transfers require an idle frozen checkpoint. Continuation creates a
          linked run with the same suite and fresh evaluation. Handoff changes
          this run’s driver and owner.
        </p>
        <div className={s.fields}>
          <label>
            Next driver
            <select
              value={driver}
              onChange={(event) => {
                setDriver(event.target.value as "managed" | "external");
                setActor(
                  event.target.value === "external" ? "coding-agent" : "user",
                );
              }}
            >
              <option value="external">External agent</option>
              <option value="managed">Built-in agent</option>
            </select>
          </label>
          <label>
            Next owner
            <input
              required
              value={actor}
              onChange={(event) => setActor(event.target.value)}
            />
          </label>
        </div>
        <label>
          Handoff reason / continuation focus
          <input
            value={reason}
            maxLength={2000}
            onChange={(event) => setReason(event.target.value)}
          />
        </label>
        <label>
          Continuation seed
          <select
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
          >
            <option value="">Select a design</option>
            {e.candidates.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title} · {c.iteration + 1}
              </option>
            ))}
          </select>
        </label>
        <div className={s.fields}>
          <label>
            Continuation API budget
            <input
              type="number"
              min={0.01}
              max={1000}
              value={budget}
              onChange={(event) => setBudget(Number(event.target.value))}
            />
          </label>
          <label>
            New candidate limit
            <input
              type="number"
              min={1}
              max={20}
              value={iterations}
              onChange={(event) => setIterations(Number(event.target.value))}
            />
          </label>
        </div>
        <div className={s.actions}>
          <button
            className={s.quiet}
            disabled={
              busy ||
              !idle ||
              e.phase === "completed" ||
              !reason.trim() ||
              !actor.trim() ||
              (driver === e.driver && actor === e.actor)
            }
            onClick={() =>
              mutate("handoff", {
                driver,
                new_actor: actor,
                reason,
                policy: {
                  max_candidates: iterations,
                  min_candidates: Math.min(iterations, 2),
                },
              })
            }
          >
            Hand off this experiment
          </button>
          <button
            className={s.button}
            disabled={busy || !idle || !seed || !actor.trim()}
            onClick={() =>
              mutate("continue", {
                candidate_id: seed,
                driver,
                new_actor: actor,
                focus: reason,
                budget_usd: budget,
                policy: {
                  max_candidates: iterations,
                  min_candidates: Math.min(iterations, 2),
                },
              })
            }
          >
            Start continuation
          </button>
        </div>
        {e.handoffs?.map((h, i) => (
          <p key={i}>
            {h.from_actor} ({h.from_driver}) → {h.to_actor} ({h.to_driver}):{" "}
            {h.reason}
          </p>
        ))}
      </section>
    </div>
  );
}
