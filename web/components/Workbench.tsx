"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  Box,
  BrainCircuit,
  Check,
  ChevronDown,
  Circle,
  Code2,
  Cpu,
  Database,
  FlaskConical,
  GitBranch,
  Layers3,
  Loader2,
  Maximize,
  MoveUpRight,
  Play,
  RotateCcw,
  Settings2,
  ShieldCheck,
  Square,
  Terminal,
  Wrench,
  X,
} from "lucide-react";

const Viewer = dynamic(() => import("./Viewer"), {
  ssr: false,
  loading: () => <div className="viewer-loading">Preparing the workbench…</div>,
});
type Doc = { _id: string; [key: string]: any };
type Data = {
  runs: Doc[];
  candidates: Doc[];
  evaluations: Doc[];
  events: Doc[];
  tools: Doc[];
  releases: Doc[];
  champions: Doc[];
  assemblies: Doc[];
  active_release_id: string;
  memory_count: number;
  storage: string;
  live_available: boolean;
};
const empty: Data = {
  runs: [],
  candidates: [],
  evaluations: [],
  events: [],
  tools: [],
  releases: [],
  champions: [],
  assemblies: [],
  active_release_id: "release-baseline",
  memory_count: 0,
  storage: "connecting",
  live_available: false,
};
const short = (s: string) => s?.replace("candidate-run-", "").slice(-18);
const time = (s: string) =>
  new Date(s).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

export default function Workbench() {
  const [data, setData] = useState<Data>(empty),
    [tab, setTab] = useState("Workbench"),
    [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [selected, setSelected] = useState(""),
    [view, setView] = useState("iso"),
    [wireframe, setWireframe] = useState(false);
  const [mode, setMode] = useState("replay"),
    [busy, setBusy] = useState(false),
    [detail, setDetail] = useState("Evaluation");
  const [rounds, setRounds] = useState(4),
    [budget, setBudget] = useState(10);
  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/workbench");
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail);
      setData(body);
      setConnectionError("");
    } catch (e) {
      setConnectionError(e instanceof Error ? e.message : "Connection failed");
    }
  }, []);
  useEffect(() => {
    setSelected(
      new URLSearchParams(window.location.search).get("candidate") || "",
    );
    refresh();
    const timer = setInterval(refresh, 2500);
    return () => clearInterval(timer);
  }, [refresh]);
  const run = data.runs[0],
    running = run?.status === "running";
  useEffect(() => {
    if (!run?._id) return;
    const events = new EventSource(`/api/runs/${run._id}/events`);
    events.onmessage = () => refresh();
    return () => events.close();
  }, [run?._id, refresh]);
  const candidate =
    data.candidates.find((c) => c._id === selected) ||
    data.candidates.find((c) =>
      data.evaluations.some(
        (e) => e.candidate_id === c._id && e.artifacts?.["model.glb"],
      ),
    ) ||
    data.candidates[0];
  const componentEvaluation = data.evaluations.find(
    (e) => e.candidate_id === candidate?._id,
  );
  const assembly = !selected
    ? data.assemblies.find(
        (a) => a.outcome === "passed" && a.artifacts?.["assembly.glb"],
      )
    : undefined;
  const evaluation = assembly
    ? {
        ...assembly,
        metrics: { mass_kg: { value: assembly.mass_kg, unit: "kg" } },
        artifacts: {
          "model.glb": assembly.artifacts["assembly.glb"],
          "model.step": assembly.artifacts["assembly.step"],
        },
      }
    : componentEvaluation;
  const glb = evaluation?.artifacts?.["model.glb"];
  const champion = [...data.champions].sort(
    (a, b) => a.objective - b.objective,
  )[0];
  const release = data.releases.find((r) => r._id === data.active_release_id);
  async function action(path: string, body?: object) {
    setBusy(true);
    setError("");
    try {
      const r = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      const b = await r.json();
      if (!r.ok) throw new Error(b.detail || "Action failed");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="app-shell">
      <aside className="rail">
        <a className="brand" href="/" aria-label="Da Vinci home">
          <span className="brand-mark">
            d<span>v</span>
          </span>
        </a>
        <div className="rail-line" />
        {[
          ["Workbench", Box],
          ["Memory", BrainCircuit],
          ["Tools", Wrench],
          ["Archive", Layers3],
        ].map(([label, Icon]) => {
          const Component = Icon as typeof Box;
          return (
            <button
              key={label as string}
              className={`rail-item ${tab === label ? "active" : ""}`}
              title={label as string}
              aria-label={label as string}
              onClick={() => setTab(label as string)}
            >
              <Component size={20} />
              <span>{label as string}</span>
            </button>
          );
        })}
        <div className="rail-bottom">
          <button
            className={`rail-item ${tab === "Settings" ? "active" : ""}`}
            onClick={() => setTab("Settings")}
            aria-label="Settings"
          >
            <Settings2 size={20} />
            <span>Settings</span>
          </button>
          <div className="avatar">DV</div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            <span>DA VINCI</span>
            <span className="slash">/</span>
            <span>Engineering workspace</span>
            <ChevronDown size={13} />
          </div>
          <div className="topbar-right">
            <span className="connection">
              <i className={connectionError ? "off" : ""} />
              {connectionError ? "Disconnected" : "System online"}
            </span>
            <span className="top-tag">ATLAS HACKATHON</span>
          </div>
        </header>
        <section className="page-heading">
          <div>
            <div className="eyebrow">AUTONOMOUS ENGINEERING LAB</div>
            <h1>
              {tab === "Workbench"
                ? "CAD workbench"
                : tab === "Memory"
                  ? "Every iteration leaves a lesson."
                  : tab === "Tools"
                    ? "A toolkit that builds itself."
                    : tab === "Archive"
                      ? "Progress, with provenance."
                      : "Your engineering environment."}
            </h1>
            <p>
              {tab === "Workbench"
                ? "CAD generation, evaluation, tools and run history."
                : tab === "Memory"
                  ? "Successful designs and geometric failures become context for the next attempt."
                  : tab === "Tools"
                    ? "Agent-authored Python utilities, tested independently and saved for reuse."
                    : tab === "Archive"
                      ? "Reproducible snapshots of geometry, evaluations, and the agents that made them."
                      : "Local execution, cloud reasoning, and a permanent engineering ledger."}
            </p>
          </div>
          <div className="heading-actions">
            <span className="version">
              <GitBranch size={13} />
              {data.active_release_id === "release-baseline"
                ? "baseline"
                : data.active_release_id.slice(0, 16)}
            </span>
            {running ? (
              <button
                className="button stop"
                disabled={busy}
                onClick={() => action(`/api/runs/${run._id}/stop`)}
              >
                <Square size={14} />
                Stop run
              </button>
            ) : (
              <button
                className="button primary"
                disabled={busy || (mode === "live" && !data.live_available)}
                onClick={() =>
                  action("/api/projects/uas-demo/runs", {
                    mode,
                    rounds,
                    budget_usd: budget,
                  })
                }
              >
                {busy ? (
                  <Loader2 className="spin" size={15} />
                ) : (
                  <Play size={14} fill="currentColor" />
                )}
                Start {mode === "replay" ? "replay" : "Astra"} run
              </button>
            )}
          </div>
        </section>
        {(error || connectionError) && (
          <div className="error" role="alert">
            <Activity size={16} />
            {error || connectionError}
            <button onClick={() => setError("")} aria-label="Dismiss error">
              <X size={16} />
            </button>
          </div>
        )}
        <div className="project-strip">
          <div>
            <span className="project-icon">
              <Layers3 size={18} />
            </span>
            <strong>UAS / Sensor & control surface</strong>
            <span className="pill">SCREENING PROTOTYPE</span>
          </div>
          <div className="strip-right">
            <span className="mono">
              {run
                ? `RUN ${run._id.slice(-6).toUpperCase()}`
                : "READY TO EXPLORE"}
            </span>
            <select
              aria-label="Run mode"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              disabled={running}
            >
              <option value="replay">Deterministic replay</option>
              <option value="live" disabled={!data.live_available}>
                Astra live{!data.live_available ? " · key required" : ""}
              </option>
            </select>
          </div>
        </div>
        {tab === "Workbench" && (
          <>
            <div className="stats">
              <Stat
                label="DESIGN ITERATIONS"
                value={String(data.candidates.length).padStart(2, "0")}
                note={
                  running
                    ? `Round ${run.round + 1} of ${run.max_rounds} · ${run.phase}`
                    : "Versioned, reproducible candidates"
                }
                icon={<GitBranch size={16} />}
              />
              <Stat
                label="BEST ASSEMBLY MASS"
                value={
                  champion ? `${(champion.mass_kg * 1000).toFixed(1)}` : "—"
                }
                unit={champion ? "g" : ""}
                note="Shared mount + surface budget: 720 g"
                icon={<Box size={16} />}
              />
              <Stat
                label="REUSABLE TOOLS"
                value={String(
                  data.tools.filter((t) => t.status === "active").length,
                ).padStart(2, "0")}
                note="Validated Python utilities"
                icon={<Wrench size={16} />}
              />
              <Stat
                label="ENGINEERING MEMORY"
                value={String(data.memory_count).padStart(2, "0")}
                note={
                  data.storage === "atlas"
                    ? "Atlas Vector Search enabled"
                    : "Persistent local replay ledger"
                }
                icon={<Database size={16} />}
              />
            </div>
            <div className="workspace-grid">
              <section className="viewer-panel">
                <div className="panel-heading">
                  <div>
                    <span className="panel-dot" />
                    <h2>Design workbench</h2>
                    <span className="muted">
                      /{" "}
                      {assembly
                        ? "Shared assembly"
                        : candidate?.subsystem === "structural"
                          ? "Sensor mount"
                          : candidate
                            ? "Control surface"
                            : "Assembly preview"}
                    </span>
                  </div>
                  <div className="viewer-tools">
                    <button
                      aria-label="View shared assembly"
                      title="View shared assembly"
                      onClick={() => setSelected("")}
                    >
                      <Layers3 size={16} />
                    </button>
                    <button
                      aria-label="Toggle wireframe"
                      title="Toggle wireframe"
                      onClick={() => setWireframe(!wireframe)}
                      className={wireframe ? "selected" : ""}
                    >
                      <Box size={16} />
                    </button>
                    <button
                      aria-label="Reset camera"
                      title="Reset camera"
                      onClick={() =>
                        setView(view === "iso" ? "iso-reset" : "iso")
                      }
                    >
                      <RotateCcw size={16} />
                    </button>
                  </div>
                </div>
                <div className="viewport">
                  <Viewer
                    key={glb || "reference"}
                    url={glb ? `/api/artifacts/${glb}` : undefined}
                    view={view}
                    wireframe={wireframe}
                  />
                  <div className="viewport-label">
                    <span className="live-dot" />
                    {glb ? "EVALUATED CAD GEOMETRY" : "REFERENCE PREVIEW"}
                    <small>
                      {glb
                        ? "STEP → GLB · millimetres"
                        : "Start a run to generate measured geometry"}
                    </small>
                  </div>
                  <div className="axes">
                    <span className="axis-y">Y</span>
                    <span className="axis-z">Z</span>
                    <span className="axis-x">X</span>
                    <i />
                  </div>
                  <div className="camera-controls">
                    <button
                      className={view.startsWith("iso") ? "selected" : ""}
                      aria-label="Isometric view"
                      onClick={() => setView("iso")}
                    >
                      ISO
                    </button>
                    <button
                      className={view === "top" ? "selected" : ""}
                      aria-label="Top view"
                      onClick={() => setView("top")}
                    >
                      TOP
                    </button>
                    <button
                      className={view === "side" ? "selected" : ""}
                      aria-label="Side view"
                      onClick={() => setView("side")}
                    >
                      SIDE
                    </button>
                  </div>
                  <span className="viewport-hint">
                    Drag to orbit · Scroll to zoom
                  </span>
                </div>
                <div className="viewer-footer">
                  <span>
                    <ShieldCheck size={14} />
                    Independent geometry evaluation
                  </span>
                  {evaluation?.artifacts?.["model.step"] ? (
                    <a
                      href={`/api/artifacts/${evaluation.artifacts["model.step"]}`}
                      download="model.step"
                    >
                      <ArrowDownToLine size={14} />
                      Export STEP
                    </a>
                  ) : (
                    <span className="muted">No geometry exported yet</span>
                  )}
                </div>
              </section>
              <section className="agents-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Agent team</h2>
                    <span className="count">02</span>
                  </div>
                  <span className="small-status">
                    {running ? "WORKING" : "STANDBY"}
                  </span>
                </div>
                <Agent
                  role="Structural"
                  description="Lightweight sensor mounts"
                  icon={<Box size={19} />}
                  data={data}
                  running={running}
                  onSelect={setSelected}
                />
                <Agent
                  role="Aerodynamic"
                  description="VTOL surfaces & control geometry"
                  icon={<Activity size={19} />}
                  data={data}
                  running={running}
                  onSelect={setSelected}
                />
                <div className="meta-agent">
                  <div className="meta-title">
                    <BrainCircuit size={18} />
                    <strong>Meta-agent</strong>
                    <span className="mini-pill">REFLECTION</span>
                  </div>
                  <p>
                    {release?.summary ||
                      "Observes failures, creates tools, and proposes tested improvements to the harness."}
                  </p>
                  <div className="loop">
                    <span>Evaluate</span>
                    <ArrowRight size={12} />
                    <span>Reflect</span>
                    <ArrowRight size={12} />
                    <span>Improve</span>
                  </div>
                </div>
                <div className="policy-frame">
                  <iframe
                    title="Active agent-authored UI component"
                    sandbox=""
                    src={`/api/releases/active/ui?v=${data.active_release_id}`}
                  />
                </div>
              </section>
            </div>
            <div className="lower-grid">
              <section className="history-panel">
                <div className="panel-heading">
                  <div>
                    <h2>Iteration ledger</h2>
                    <span className="count">{data.candidates.length}</span>
                  </div>
                  <span className="muted">Every attempt, preserved.</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>ITERATION</th>
                        <th>SPECIALIST</th>
                        <th>MASS</th>
                        <th>RESULT</th>
                        <th>REVISION</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.candidates.slice(0, 8).map((c) => {
                        const e = data.evaluations.find(
                          (x) => x.candidate_id === c._id,
                        );
                        return (
                          <tr
                            key={c._id}
                            onClick={() => setSelected(c._id)}
                            className={c._id === candidate?._id ? "chosen" : ""}
                            tabIndex={0}
                            onKeyDown={(event) => {
                              if (event.key === "Enter") setSelected(c._id);
                            }}
                          >
                            <td>
                              <span className="iteration-no">
                                {String(c.round + 1).padStart(2, "0")}
                              </span>
                              <span className="subtle">
                                {c.subsystem === "structural" ? "MNT" : "AER"}
                              </span>
                            </td>
                            <td>
                              {c.subsystem === "structural"
                                ? "Structural"
                                : "Aerodynamic"}
                            </td>
                            <td className="mono">
                              {e?.metrics?.mass_kg
                                ? `${(e.metrics.mass_kg.value * 1000).toFixed(1)} g`
                                : "—"}
                            </td>
                            <td>
                              <Status value={e?.outcome || "pending"} />
                            </td>
                            <td className="mono subtle">
                              {c.source_commit?.slice(0, 7)}
                              <MoveUpRight size={12} />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  {!data.candidates.length && (
                    <div className="empty">
                      <GitBranch size={25} />
                      <strong>Your first iteration starts here</strong>
                      <p>
                        Run the replay to watch a failure become a reusable
                        improvement.
                      </p>
                    </div>
                  )}
                </div>
              </section>
              <section className="evaluation-panel">
                <div className="detail-tabs">
                  {["Evaluation", "Source"].map((t) => (
                    <button
                      key={t}
                      className={detail === t ? "active" : ""}
                      onClick={() => setDetail(t)}
                    >
                      {t}
                    </button>
                  ))}
                  {evaluation && <Status value={evaluation.outcome} />}
                </div>
                {detail === "Source" ? (
                  <pre className="code">
                    {assembly
                      ? JSON.stringify(
                          {
                            components: assembly.candidate_ids,
                            transform_mm: assembly.mount_translation_mm,
                          },
                          null,
                          2,
                        )
                      : candidate?.source ||
                        "# Generated CadQuery source will appear here."}
                  </pre>
                ) : (
                  <div className="evaluation-body">
                    <div className="evaluation-caption">
                      {assembly
                        ? `SHARED ASSEMBLY / ROUND ${assembly.round + 1}`
                        : candidate
                          ? `${candidate.subsystem.toUpperCase()} / ROUND ${candidate.round + 1}`
                          : "AWAITING FIRST CANDIDATE"}
                    </div>
                    {evaluation ? (
                      Object.entries(evaluation.metrics || {})
                        .slice(0, 5)
                        .map(([key, m]: [string, any]) => (
                          <div className="metric-row" key={key}>
                            <span>
                              {key
                                .replaceAll("_", " ")
                                .replace(/ kg$| mm$| pa$| n$/, "")}
                            </span>
                            <strong>
                              {Number(m.value).toLocaleString(undefined, {
                                maximumFractionDigits: 4,
                              })}
                              <small>{m.unit}</small>
                            </strong>
                          </div>
                        ))
                    ) : (
                      <p className="placeholder-copy">
                        Geometry, mass, stress, and clearance checks appear
                        after independent evaluation.
                      </p>
                    )}
                    {evaluation?.violations?.map((v: any) => (
                      <div className="violation" key={v.code}>
                        <span>{v.code.replaceAll("_", " ")}</span>
                        {v.message}
                      </div>
                    ))}
                    <div className="fidelity">
                      <FlaskConical size={15} />
                      <span>Analytic screening · not flight validation</span>
                    </div>
                    {glb && !assembly && (
                      <button
                        className="text-button"
                        onClick={() =>
                          action(`/api/candidates/${candidate._id}/inspect`)
                        }
                        disabled={busy}
                      >
                        Inspect in browser
                        <MoveUpRight size={13} />
                      </button>
                    )}
                  </div>
                )}
              </section>
            </div>
            <section className="activity-panel">
              <div className="panel-heading">
                <div>
                  <Terminal size={16} />
                  <h2>Live activity</h2>
                </div>
                <span className="small-status">
                  {run?.mode === "live" ? "GPT-6 ASTRA" : "REPLAY ENGINE"}
                </span>
              </div>
              {data.events.slice(0, 5).map((e) => (
                <div className="activity-row" key={e._id}>
                  <time>{time(e.created_at)}</time>
                  <span
                    className={`event-dot ${e.kind.includes("fail") || e.kind.includes("error") ? "warning" : ""}`}
                  />
                  <span>{e.message}</span>
                  <code>{e.kind}</code>
                </div>
              ))}
              {!data.events.length && (
                <div className="activity-row">
                  <time>—</time>
                  <span className="event-dot" />
                  <span>Workbench ready. Waiting for your first run.</span>
                  <code>idle</code>
                </div>
              )}
            </section>
          </>
        )}
        {tab === "Memory" && (
          <section className="collection-page">
            <div className="collection-heading">
              <h2>{data.memory_count} recorded outcomes</h2>
              <span>
                {data.storage === "atlas"
                  ? "Semantic retrieval + structured filters"
                  : "Local lexical retrieval · Atlas enables vector search"}
              </span>
            </div>
            {data.evaluations.map((e) => (
              <article className="memory-card" key={e._id}>
                <div>
                  <Status value={e.outcome} />
                  <span className="mono">
                    {e.subsystem} / round {e.round + 1}
                  </span>
                </div>
                <h3>
                  {e.violations?.length
                    ? e.violations[0].code.replaceAll("_", " ")
                    : "Feasible geometry archived"}
                </h3>
                <p>
                  {e.violations?.map((v: any) => v.message).join(" · ") ||
                    "Successful parameters and measured metrics are available to subsequent iterations."}
                </p>
                <button
                  className="text-button"
                  onClick={() => {
                    setSelected(e.candidate_id);
                    setTab("Workbench");
                  }}
                >
                  Inspect evidence
                  <ArrowRight size={14} />
                </button>
              </article>
            ))}
            {!data.evaluations.length && (
              <Empty
                icon={<BrainCircuit />}
                title="Memory begins with an experiment"
                text="Start a replay run. Both successful and failed designs will be preserved here."
              />
            )}
          </section>
        )}
        {tab === "Tools" && (
          <section className="collection-page">
            <div className="collection-heading">
              <h2>Permanent tool repository</h2>
              <span>
                Versioned source · Independent fixtures · Isolated execution
              </span>
            </div>
            {data.tools.map((t) => (
              <article className="tool-card" key={t._id}>
                <div className="tool-icon">
                  <Code2 />
                </div>
                <div>
                  <div className="card-topline">
                    <h3>{t.name}</h3>
                    <Status value={t.status} />
                  </div>
                  <p>{t.summary}</p>
                  <code>{t.entrypoint}</code>
                  <div className="test-list">
                    {t.validation.map((check: any, i: number) => (
                      <span key={i} className={check.passed ? "pass" : "fail"}>
                        {check.passed ? <Check size={13} /> : <X size={13} />}{" "}
                        {check.name || `Reference ${i + 1}`}
                      </span>
                    ))}
                  </div>
                  <div className="source-link">
                    <GitBranch size={13} />
                    {t.source_commit.slice(0, 12)}
                    <span>Network disabled · 60 s limit</span>
                  </div>
                </div>
              </article>
            ))}
            {!data.tools.length && (
              <Empty
                icon={<Wrench />}
                title="Tools emerge from missing capabilities"
                text="The reflection loop will write, test, and archive a reusable Python utility after its first failure."
              />
            )}
          </section>
        )}
        {tab === "Archive" && (
          <section className="collection-page">
            <div className="collection-heading">
              <h2>Champion states & harness releases</h2>
              {run && (
                <a
                  className="button secondary"
                  href={`/api/runs/${run._id}/bundle`}
                >
                  <ArrowDownToLine size={14} />
                  Export run bundle
                </a>
              )}
            </div>
            <div className="archive-grid">
              {data.champions.map((c) => (
                <article className="champion-card" key={c._id}>
                  <div className="eyebrow">FEASIBLE ASSEMBLY</div>
                  <h3>
                    {(c.mass_kg * 1000).toFixed(1)}
                    <small>g</small>
                  </h3>
                  <p>
                    {c.induced_drag_n.toFixed(4)} N induced-drag screening
                    estimate
                  </p>
                  <span className="mono">
                    Objective {c.objective.toFixed(4)}
                  </span>
                  <button
                    className="text-button"
                    onClick={() => {
                      setSelected(c.candidate_ids[0]);
                      setTab("Workbench");
                    }}
                  >
                    Open geometry
                    <ArrowRight size={13} />
                  </button>
                </article>
              ))}
            </div>
            <h2 className="section-title">Harness history</h2>
            {data.releases.map((r) => (
              <article className="release-card" key={r._id}>
                <GitBranch size={20} />
                <div>
                  <h3>{r.summary}</h3>
                  <span className="mono">
                    {r.source_commit?.slice(0, 12)} · {r._id}
                  </span>
                  <div className="test-list">
                    {r.validation?.map((c: any, i: number) => (
                      <span key={i} className={c.passed ? "pass" : "fail"}>
                        {c.passed ? <Check size={12} /> : <X size={12} />}{" "}
                        {c.name}
                      </span>
                    ))}
                  </div>
                </div>
                <Status
                  value={r._id === data.active_release_id ? "active" : r.status}
                />
              </article>
            ))}
          </section>
        )}
        {tab === "Settings" && (
          <section className="settings-page">
            <article>
              <h2>Run controls</h2>
              <label>
                Maximum design rounds
                <input
                  aria-label="Maximum design rounds"
                  type="number"
                  min={1}
                  max={10}
                  value={rounds}
                  onChange={(e) =>
                    setRounds(Math.max(1, Math.min(10, Number(e.target.value))))
                  }
                />
              </label>
              <label>
                API budget per run (USD)
                <input
                  aria-label="API budget per run"
                  type="number"
                  min={1}
                  max={50}
                  value={budget}
                  onChange={(e) =>
                    setBudget(Math.max(1, Math.min(50, Number(e.target.value))))
                  }
                />
              </label>
              <p>
                Server limits also apply. Replay runs do not make paid model
                calls.
              </p>
            </article>
            <article>
              <h2>Connections</h2>
              <div className="metric-row">
                <span>Storage</span>
                <strong>{data.storage}</strong>
              </div>
              <div className="metric-row">
                <span>GPT-6 Astra</span>
                <strong>
                  {data.live_available ? "Configured" : "Key not configured"}
                </strong>
              </div>
              <p>
                Set <code>MONGODB_URI</code> and <code>OPENAI_API_KEY</code> in
                the project’s server-side <code>.env</code>, then restart the
                API and workers.
              </p>
            </article>
            <article>
              <h2>Execution envelope</h2>
              <p>
                Two CAD workers · 2 CPUs and 4 GiB per container · Network
                disabled · Fixed acceptance tests · Automatic rollback
              </p>
              <p>
                Engineering results are screening estimates. Every exported run
                includes the assumptions and evaluator version.
              </p>
            </article>
          </section>
        )}
        <footer>
          <span>
            <span className="footer-mark">dv</span>DA VINCI{" "}
            <span className="subtle">/</span> ENGINEERING, ITERATED.
          </span>
          <span>
            CadQuery <i /> Python <i /> MongoDB Atlas
          </span>
        </footer>
      </main>
    </div>
  );
}

function Stat({
  label,
  value,
  unit,
  note,
  icon,
}: {
  label: string;
  value: string;
  unit?: string;
  note: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="stat">
      <div className="stat-label">
        {label}
        {icon}
      </div>
      <div className="stat-value">
        {value}
        <small>{unit}</small>
      </div>
      <p>{note}</p>
    </div>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span
      className={`status ${["passed", "active", "validated"].includes(value) ? "good" : value === "failed" || value === "rejected" ? "bad" : "pending"}`}
    >
      <i />
      {value}
    </span>
  );
}
function Empty({
  icon,
  title,
  text,
}: {
  icon: React.ReactNode;
  title: string;
  text: string;
}) {
  return (
    <div className="empty large">
      {icon}
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function Agent({
  role,
  description,
  icon,
  data,
  running,
  onSelect,
}: {
  role: string;
  description: string;
  icon: React.ReactNode;
  data: Data;
  running: boolean;
  onSelect: (s: string) => void;
}) {
  const candidate = data.candidates.find(
    (c) => c.subsystem === role.toLowerCase(),
  );
  const result = data.evaluations.find(
    (e) => e.candidate_id === candidate?._id,
  );
  return (
    <button
      className={`agent-card ${role === "Structural" ? "structural" : "aero"}`}
      onClick={() => candidate && onSelect(candidate._id)}
    >
      <div className="agent-title">
        <span className="agent-icon">{icon}</span>
        <div>
          <h3>
            {role}
            <span>AGENT {role === "Structural" ? "01" : "02"}</span>
          </h3>
          <p>{description}</p>
        </div>
        <span className={`agent-light ${running ? "working" : ""}`} />
      </div>
      <div className="agent-bottom">
        <span>
          {result?.outcome === "passed" ? (
            <Check size={13} />
          ) : running ? (
            <Loader2 size={13} className="spin" />
          ) : (
            <Circle size={11} />
          )}{" "}
          {result
            ? result.outcome === "passed"
              ? "Screening passed"
              : "Refining after evaluation"
            : running
              ? "Generating candidate"
              : "Ready for assignment"}
        </span>
        <ArrowRight size={14} />
      </div>
    </button>
  );
}
