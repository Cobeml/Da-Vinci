"use client";

import dynamic from "next/dynamic";
import { useEffect, useId, useRef, useState } from "react";
import { ArrowDown, ArrowDownToLine, Check, Maximize2, X } from "lucide-react";
import ResearchEvidence from "./ResearchEvidence";
import styles from "./SensorGallery.module.css";
import grip from "./GripperGallery.module.css";

const Viewer = dynamic(() => import("./GripperViewer"), {
  ssr: false,
  loading: () => <div className={styles.loading}>Loading CAD…</div>,
});
type Metric = { value: number; unit: string; fidelity: string };
type Design = {
  _id: string;
  iteration: number;
  title: string;
  change: string;
  parameters: { depth_mm: number; nodes: number[][]; edges: number[][] };
  assets: Record<string, string>;
  tool_id: string | null;
  reflection: { lesson: string; next_focus: string };
  evaluation: {
    outcome: string;
    metrics: Record<string, Metric>;
    violations: { code: string; message: string }[];
    load_cases?: { name: string; members: { stress_mpa: number }[] }[];
  };
};
export type GripperData = {
  designs: Design[];
  best_id: string | null;
  reduction_percent: number;
  publishable: boolean;
  spent_usd: number;
};
const mass = (d: Design) => d.evaluation.metrics.mass_g?.value;

function ModelView({
  design,
  overview = false,
  expanded = false,
  initialMounted = false,
}: {
  design: Design;
  overview?: boolean;
  expanded?: boolean;
  initialMounted?: boolean;
}) {
  const [gap, setGap] = useState(60),
    [frame, setFrame] = useState(false),
    [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(initialMounted);
  const dialog = useRef<HTMLDialogElement>(null),
    sliderId = useId();
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  if (!design.assets["model.glb"])
    return (
      <div className={grip.noModel}>
        CAD build failed · recorded for the next attempt
      </div>
    );
  const stresses = design.parameters.edges.map((_, i) =>
    Math.max(
      0,
      ...(design.evaluation.load_cases || []).map(
        (c) => c.members[i]?.stress_mpa || 0,
      ),
    ),
  );
  return (
    <>
      <div
        className={`${styles.modelView} ${grip.model} ${overview ? grip.overview : ""} ${expanded ? grip.expanded : ""}`}
      >
        <div className={styles.viewBar}>
          <div className={grip.viewGroups}>
            <div
              className={styles.segment}
              role="group"
              aria-label="Assembly view"
            >
              <button aria-pressed={!mounted} onClick={() => setMounted(false)}>
                Gripper
              </button>
              <button aria-pressed={mounted} onClick={() => setMounted(true)}>
                On VTOL
              </button>
            </div>
            <div
              className={styles.segment}
              role="group"
              aria-label="Analysis view"
            >
              <button aria-pressed={!frame} onClick={() => setFrame(false)}>
                CAD
              </button>
              <button aria-pressed={frame} onClick={() => setFrame(true)}>
                Frame stress
              </button>
            </div>
          </div>
          {!expanded && (
            <div className={styles.viewActions}>
              <button
                aria-label={`Expand iteration ${design.iteration}`}
                onClick={() => setOpen(true)}
              >
                <Maximize2 size={15} />
              </button>
            </div>
          )}
        </div>
        <Viewer
          assets={design.assets}
          parameters={design.parameters}
          gap={gap}
          frame={frame}
          stresses={stresses}
          mounted={mounted}
        />
        <div className={grip.opening}>
          <label htmlFor={sliderId}>
            Opening <strong>{gap} mm</strong>
          </label>
          <input
            id={sliderId}
            aria-label="Jaw opening"
            type="range"
            min={20}
            max={60}
            step={1}
            value={gap}
            onChange={(event) => setGap(Number(event.target.value))}
          />
        </div>
        {frame && (
          <span className={grip.legend}>
            Nominal stress <i /> 0 → 80 MPa
          </span>
        )}
      </div>
      {!expanded && (
        <dialog
          ref={dialog}
          className={styles.modal}
          onCancel={() => setOpen(false)}
          onClick={(event) => {
            if (event.target === dialog.current) setOpen(false);
          }}
        >
          <div className={styles.modalHeader}>
            <span>
              Iteration {String(design.iteration).padStart(2, "0")} ·{" "}
              {design.title}
            </span>
            <button
              aria-label="Close expanded model"
              onClick={() => setOpen(false)}
            >
              <X size={20} />
            </button>
          </div>
          {open && (
            <ModelView design={design} expanded initialMounted={mounted} />
          )}
        </dialog>
      )}
    </>
  );
}

export default function GripperGallery({ data }: { data: GripperData }) {
  const best = data.designs.find((d) => d._id === data.best_id);
  if (!best)
    return (
      <main className={styles.page}>
        <h1>Da Vinci</h1>
        <p>Gripper study awaiting a passing design.</p>
      </main>
    );
  const baseline = data.designs[0],
    maximum = Math.max(...data.designs.map((d) => mass(d) || 0));
  let bestSoFar = Infinity;
  const improved = new Set<string>();
  for (const design of data.designs) {
    if (
      design.evaluation.outcome === "passed" &&
      mass(design) < bestSoFar - 0.1
    ) {
      bestSoFar = mass(design);
      improved.add(design._id);
    }
  }
  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>
            Da Vinci <span>Recursive Improvement CAD Harness</span>
          </h1>
          <p>
            Parallel-jaw gripper · {data.designs.length} GPT-6 Astra iterations
          </p>
        </div>
        <span className={styles.material}>
          100 N pinch · 4 load cases · 3 parts
        </span>
      </header>
      <section className={styles.overview} aria-label="Project overview">
        <div className={grip.hero} data-testid="overview-model">
          <ModelView design={best} overview />
        </div>
        <div className={styles.overviewText}>
          <section aria-labelledby="methods-heading">
            <h2 id="methods-heading">Self-improvement methods</h2>
            <p className={styles.methodIntro}>
              The agent designs the finger’s rib layout, learns from measured
              loads and reuses its own tools. Model weights stay fixed.
            </p>
            <div className={styles.method}>
              <h3>1. Reflect and remember</h3>
              <p>
                Review stress, displacement and clearance results. Retrieve
                prior attempts with Atlas Vector Search and carry lessons
                forward.
              </p>
            </div>
            <div className={styles.method}>
              <h3>2. Create and reuse tools</h3>
              <p>
                Write a member-sizing utility, pass six independent checks and
                execute it before subsequent designs.
              </p>
            </div>
            <div className={styles.method}>
              <h3>3. Evaluate and revise</h3>
              <p>
                Change rib connectivity, dimensions and depth. Keep the lightest
                jaw pair that passes every fixed check.
              </p>
            </div>
            <ResearchEvidence />
          </section>
          <section className={styles.atlas}>
            <h2>MongoDB Atlas</h2>
            <p>
              <strong>Documents</strong> store attempts, evaluations, tools and
              policies. <strong>Vector Search</strong> retrieves prior results.{" "}
              <strong>GridFS</strong> preserves CAD files and source snapshots.
            </p>
          </section>
          <details className={styles.disclosure}>
            <summary>Agent harness setup</summary>
            <div className={styles.disclosureBody}>
              <h3>Generate, evaluate, reflect</h3>
              <p>
                Astra uses high reasoning to choose nodes, rib connections and
                rectangular sections within fixed carriage and contact
                interfaces. CadQuery builds the guide base and two mirrored jaws
                in an isolated Docker container.
              </p>
              <p>
                A separate evaluator verifies the exported STEP geometry, checks
                collisions at nine openings from 20 to 60 mm and tests contact
                with 20 mm and 60 mm sample gauges. A linear 3D beam-frame
                solver evaluates pinch, payload, lateral and combined loads.
              </p>
              <p>
                A review-agent call interprets every measured result and saves
                the next working policy. After the first two attempts, a
                generated sizing utility passes independent tests before reuse.
                Atlas memories and actual tool outputs enter later design
                prompts. Git versions source and context.
              </p>
              <h3>Fixed acceptance checks</h3>
              <p>
                Nominal stress ≤ 80 MPa, tip displacement ≤ 0.25 mm, member
                buckling factor ≥ 2 and running clearance ≥ 0.25 mm. The
                objective is moving jaw-pair mass; the unchanged guide base is
                included only in total assembly mass.
              </p>
              <h3>Measurement scope</h3>
              <p>
                Mass is measured from STEP volume at nominal aluminium density.
                Structural results use ideal rigid beam joints and fixed
                carriage roots, with loads applied at the defined tip node. Pad
                offset couples, fillets, bearings and contact are not modeled.
                The actuator, friction pads, fatigue, local shear and torsional
                stresses are outside this study. The drone and mounting adapter
                are display context; installation and flight loads have not been
                evaluated.
              </p>
              <p>
                This sequential study uses the same archive, memory and sandbox
                services as the{" "}
                <a href="/harness">full multi-agent workbench</a>. The
                workbench’s Atlas triggers drive its two-specialist
                evaluation/reflection queue; this study uses a Python loop.
                Recorded API usage: ${data.spent_usd.toFixed(2)} within a $25
                cap.
              </p>
            </div>
          </details>
        </div>
      </section>
      <div className={styles.sectionHeading}>
        <h2>All {data.designs.length} design iterations</h2>
        <span>Moving jaw mass · fixed guide base excluded</span>
      </div>
      <section className={styles.progress} aria-label="Design progress">
        <div className={styles.progressSummary}>
          <span className={styles.eyebrow}>BEST PASSING JAW PAIR</span>
          <strong>
            {mass(baseline).toFixed(1)} <span>→</span> {mass(best).toFixed(1)}{" "}
            <small>g</small>
          </strong>
          <span className={styles.reduction}>
            <ArrowDown size={15} />
            {data.reduction_percent.toFixed(1)}% moving mass reduction
          </span>
        </div>
        <div className={styles.chart}>
          {data.designs.map((d) => (
            <a
              key={d._id}
              href={`#iteration-${d.iteration}`}
              className={`${styles.barColumn} ${d._id === best._id ? styles.bestBar : ""} ${d.evaluation.outcome !== "passed" ? styles.failedBar : ""}`}
            >
              <span>
                {mass(d)?.toFixed(1) ?? "—"}
                <small> g</small>
              </span>
              <div
                style={{
                  height: `${Math.max(8, ((mass(d) || 0) / maximum) * 58)}px`,
                }}
              />
              <small>{String(d.iteration).padStart(2, "0")}</small>
            </a>
          ))}
        </div>
        <p className={styles.constraints}>
          Same checks for every design
          <br />
          Displacement ≤ 0.25 mm
          <br />
          Stress ≤ 80 MPa
        </p>
      </section>
      <section className={styles.grid} aria-label="Generated grippers">
        {data.designs.map((d) => {
          const ok = d.evaluation.outcome === "passed",
            isBest = d._id === best._id,
            m = d.evaluation.metrics;
          return (
            <article
              id={`iteration-${d.iteration}`}
              key={d._id}
              data-testid="design-card"
              className={`${styles.card} ${isBest ? styles.bestCard : ""}`}
            >
              <div className={styles.cardHeader}>
                <span className={styles.iteration}>
                  {String(d.iteration).padStart(2, "0")}
                </span>
                <h2>{d.title}</h2>
                <span className={`${styles.badge} ${ok ? "" : styles.failed}`}>
                  {isBest ? (
                    <>
                      <Check size={12} />
                      Best
                    </>
                  ) : !ok ? (
                    "Failed check"
                  ) : d.iteration === 1 ? (
                    "Baseline"
                  ) : improved.has(d._id) ? (
                    "Improved"
                  ) : (
                    "Passed"
                  )}
                </span>
              </div>
              <ModelView design={d} />
              <div className={styles.cardDetails}>
                <p className={styles.description}>
                  {d.parameters.edges.length} ribs per jaw ·{" "}
                  {d.parameters.nodes.length} frame nodes ·{" "}
                  {d.parameters.depth_mm} mm extrusion
                </p>
                <dl className={styles.metrics}>
                  <div>
                    <dt>Moving mass</dt>
                    <dd>
                      {mass(d)?.toFixed(1) ?? "—"} <small>g</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Total assembly</dt>
                    <dd>
                      {m.total_mass_g?.value.toFixed(1) ?? "—"} <small>g</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Displacement est.</dt>
                    <dd
                      className={
                        m.deflection_mm?.value > 0.25 ? styles.badValue : ""
                      }
                    >
                      {m.deflection_mm?.value.toFixed(3) ?? "—"}{" "}
                      <small>mm</small>
                    </dd>
                  </div>
                  <div>
                    <dt>Stress est.</dt>
                    <dd
                      className={
                        m.stress_mpa?.value > 80 ? styles.badValue : ""
                      }
                    >
                      {m.stress_mpa?.value.toFixed(1) ?? "—"} <small>MPa</small>
                    </dd>
                  </div>
                </dl>
                <p className={grip.checks}>
                  {ok
                    ? "4 loads + 9 openings passed"
                    : d.evaluation.violations
                        .map((v) => v.code.replaceAll("_", " ").toLowerCase())
                        .join(" · ")}
                </p>
                <details className={grip.reflection}>
                  <summary>Agent reflection</summary>
                  <p>{d.change}</p>
                  <p>{d.reflection.lesson}</p>
                  <p>{d.reflection.next_focus}</p>
                </details>
                <div className={styles.cardFooter}>
                  <span>
                    {d.tool_id
                      ? "Saved sizing tool used"
                      : "Initial topology exploration"}
                  </span>
                  {d.assets["model.step"] && (
                    <a href={d.assets["model.step"]} download>
                      <ArrowDownToLine size={13} />
                      STEP
                    </a>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </section>
      <div className={styles.bottom}>
        <a href="/sensor">Earlier sensor-mount study ↗</a>
        <a href="/harness">Full harness ↗</a>
      </div>
    </main>
  );
}
