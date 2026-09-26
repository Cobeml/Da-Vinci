"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowDownToLine, Check, Maximize2, RotateCcw, X } from "lucide-react";
import styles from "./SensorGallery.module.css";

const Viewer = dynamic(() => import("./SensorViewer"), { ssr: false, loading: () => <div className={styles.loading}>Loading CAD…</div> });
type Metric = { value: number; unit: string; fidelity: string };
type Design = {
  _id: string; iteration: number; title: string; change: string; lesson: string;
  parameters: Record<string, number>; model_url: string; step_url: string; source_url: string;
  tool_id: string | null; source_commit: string; generator: string;
  evaluation: { outcome: string; metrics: Record<string, Metric>; violations: { code: string; message: string }[] };
};
export type GalleryData = { study_id: string; generated_at: string; designs: Design[]; specification: { load_n: number; max_deflection_mm: number; allowable_stress_mpa: number; material: string } };
const mass = (d: Design) => d.evaluation.metrics.mass_g.value;
const title = (d: Design) => d.parameters.window_style === 0 ? "Solid cradle"
  : d.parameters.window_style === 2 ? "Ribbed cradle"
  : d.iteration === 2 ? "Open-window cradle" : "Open-window refinement";
function description(d: Design) {
  const p = d.parameters;
  if (!p.window_style) return `${p.base_mm} mm solid base and ${p.wall_mm} mm side walls.`;
  if (p.window_style === 2) return `Diagonal ribs, ${p.base_slots} base slots and ${p.gusset_mm} mm gussets.`;
  return `${p.wall_mm.toFixed(3)} mm walls, oval windows and one base slot.`;
}

function ModelView({ design, expanded = false }: { design: Design; expanded?: boolean }) {
  const [mounted, setMounted] = useState(false);
  const [reset, setReset] = useState(0);
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal(); else dialog.current?.close();
  }, [open]);
  return <>
    <div className={`${styles.modelView} ${expanded ? styles.expanded : ""}`}>
      <div className={styles.viewBar}>
        <div className={styles.segment} aria-label={`View for iteration ${design.iteration}`}>
          <button aria-pressed={!mounted} onClick={() => setMounted(false)}>Mount</button>
          <button aria-pressed={mounted} onClick={() => setMounted(true)}>On VTOL</button>
        </div>
        <div className={styles.viewActions}>
          <button title="Reset view" aria-label="Reset view" onClick={() => setReset(reset + 1)}><RotateCcw size={14} /></button>
          {!expanded && <button title="Expand model" aria-label={`Expand iteration ${design.iteration}`} onClick={() => setOpen(true)}><Maximize2 size={15} /></button>}
        </div>
      </div>
      <Viewer url={design.model_url} mounted={mounted} reset={reset} />
      <span className={styles.viewHint}>{mounted ? "VTOL reference · mount highlighted" : "Drag to rotate · Scroll to zoom"}</span>
    </div>
    {!expanded && <dialog ref={dialog} className={styles.modal} onCancel={() => setOpen(false)} onClick={(event) => { if (event.target === dialog.current) setOpen(false); }}>
      <div className={styles.modalHeader}><span>Iteration {String(design.iteration).padStart(2, "0")} · {title(design)}</span><button aria-label="Close expanded model" onClick={() => setOpen(false)}><X size={20} /></button></div>
      {open && <ModelView design={design} expanded />}
    </dialog>}
  </>;
}

export default function SensorGallery({ data }: { data: GalleryData }) {
  const designs = data.designs;
  const passing = designs.filter(d => d.evaluation.outcome === "passed");
  if (!passing.length) return <main className={styles.page}><h1>Da Vinci: recursive improvement CAD harness</h1><p>No passing sensor-mount designs are available yet.</p></main>;
  const baseline = passing[0];
  const best = passing.reduce((a, b) => mass(a) < mass(b) ? a : b);
  const reduction = (1 - mass(best) / mass(baseline)) * 100;
  let minimum = Infinity;
  const improved = new Set<string>();
  designs.forEach(d => { if (d.evaluation.outcome === "passed" && mass(d) < minimum - .01) { improved.add(d._id); minimum = mass(d); } });
  const maximum = Math.max(...designs.map(mass));
  return <main className={styles.page}>
    <header className={styles.header}>
      <div><h1>Da Vinci <span>/ Recursive improvement CAD harness</span></h1><p>Drone sensor mount · {designs.length} GPT-6 Astra iterations</p></div>
      <span className={styles.material}>{data.specification.material} · {data.specification.load_n} N load</span>
    </header>

    <section className={styles.progress} aria-label="Design progress">
      <div className={styles.progressSummary}><span className={styles.eyebrow}>BEST PASSING MOUNT</span><strong>{mass(baseline).toFixed(1)} <span>→</span> {mass(best).toFixed(1)} <small>g</small></strong><span className={styles.reduction}><ArrowDown size={15} />{reduction.toFixed(1)}% mass reduction</span></div>
      <div className={styles.chart} aria-label="Mass by iteration">
        {designs.map(d => <a key={d._id} href={`#iteration-${d.iteration}`} className={`${styles.barColumn} ${d._id === best._id ? styles.bestBar : ""} ${d.evaluation.outcome !== "passed" ? styles.failedBar : ""}`} aria-label={`Iteration ${d.iteration}: ${mass(d).toFixed(1)} grams, ${d.evaluation.outcome}`}>
          <span>{mass(d).toFixed(1)}<small> g</small></span><div style={{ height: `${Math.max(8, mass(d) / maximum * 58)}px` }} /><small>{String(d.iteration).padStart(2, "0")}</small>
        </a>)}
      </div>
      <p className={styles.constraints}>Same checks for every design<br />Deflection ≤ {data.specification.max_deflection_mm} mm<br />Stress ≤ {data.specification.allowable_stress_mpa} MPa</p>
    </section>

    <section className={styles.grid} aria-label="Generated sensor mounts">
      {designs.map(d => {
        const ok = d.evaluation.outcome === "passed", isBest = d._id === best._id;
        const change = (1 - mass(d) / mass(baseline)) * 100;
        return <article id={`iteration-${d.iteration}`} key={d._id} className={`${styles.card} ${isBest ? styles.bestCard : ""}`} data-testid="design-card">
          <div className={styles.cardHeader}><span className={styles.iteration}>{String(d.iteration).padStart(2, "0")}</span><h2>{title(d)}</h2><span className={`${styles.badge} ${!ok ? styles.failed : ""}`}>{isBest ? <><Check size={12} />Best</> : !ok ? "Failed check" : d._id === baseline._id ? "Baseline" : improved.has(d._id) ? "Improved" : "Passed"}</span></div>
          <ModelView design={d} />
          <div className={styles.cardDetails}>
            <p className={styles.description}>{description(d)}</p>
            <dl className={styles.metrics}>
              <div><dt>Mass</dt><dd>{mass(d).toFixed(1)} <small>g</small></dd></div>
              <div><dt>vs. baseline</dt><dd className={change > 0 && ok ? styles.good : ""}>{change > 0 ? "−" : change < 0 ? "+" : ""}{Math.abs(change).toFixed(1)}<small>%</small></dd></div>
              <div><dt>Deflection est.</dt><dd className={d.evaluation.metrics.deflection_mm.value > data.specification.max_deflection_mm ? styles.badValue : ""}>{d.evaluation.metrics.deflection_mm.value.toFixed(3)} <small>mm</small></dd></div>
              <div><dt>Stress est.</dt><dd>{d.evaluation.metrics.stress_mpa.value.toFixed(2)} <small>MPa</small></dd></div>
            </dl>
            {!ok && <p className={styles.violation}>{d.evaluation.violations.map(v => v.message).join(". ")}</p>}
            <div className={styles.cardFooter}><span>{d.tool_id ? "Saved thickness tool used" : "Initial design exploration"}</span><a href={d.step_url} download><ArrowDownToLine size={13} />STEP</a></div>
          </div>
        </article>;
      })}
    </section>

    <footer className={styles.footer}>
      <section><h2>Self-improvement methods</h2><ul><li>Retrieve prior designs and measured results.</li><li>Write and test a reusable wall-thickness tool.</li><li>Carry learned constraints into subsequent attempts.</li><li>Retain the lightest design that passes every check.</li></ul></section>
      <section><h2>MongoDB Atlas</h2><p>Documents store designs, evaluations, tools and policies. Vector Search retrieves previous results. GridFS stores the CAD files and source snapshots.</p><p className={styles.note}>Mass is measured from STEP volume. Stress and deflection use a wall-strip estimate, not FEA. The VTOL is illustrative; metrics cover the mount only.</p></section>
    </footer>
    <div className={styles.bottom}><span>100 × 72 mm mounting footprint · 80 × 52 mm bolt pattern</span><a href="/harness">Full harness ↗</a></div>
  </main>;
}
