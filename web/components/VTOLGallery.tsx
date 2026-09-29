"use client";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { ArrowDownToLine, Check, Maximize2 } from "lucide-react";
import ResearchEvidence from "./ResearchEvidence";
import styles from "./SensorGallery.module.css";
import vtol from "./VTOLGallery.module.css";
const Viewer = dynamic(() => import("./VTOLViewer"), { ssr: false, loading: () => <div className={styles.loading}>Loading CAD…</div> });
type Metric = { value: number; unit: string; fidelity: string };
type Point = { speed_m_s: number; power_w: number; range_km: number };
type Nominal = { best: { body_drag_n: number; induced_drag_n: number; profile_drag_n: number; hardware_drag_n: number; wh_km: number } | null; overhead_wh: number; reserve_wh: number; static_margin: number; hover_thrust_ratio: number; curve: Point[]; structure?: { wing: { stress_pa: number; deflection_m: number }; boom: { stress_pa: number; deflection_m: number } } };
type Evaluation = { outcome: string; metrics: Record<string, Metric>; violations: { code: string; message: string }[]; performance?: { nominal: Nominal; scenarios: Record<string, { range_km: number; violations: string[] }> } };
type Design = { _id: string; iteration: number; title: string; change: string; assets: Record<string, string>; parameters: Record<string, number>; evaluation: Evaluation; reflection: { lesson: string; next_focus: string }; tool_id: string | null };
export type VTOLData = { designs: Design[]; best_id: string | null; publishable: boolean; improvement_percent: number; spent_usd: number; validation: { validations: Record<string, { converged: boolean; evaluation: Evaluation; relative_changes: Record<string, number> }> } | null };
const value = (d: Design, key: string) => d.evaluation.metrics[key]?.value;
function Model({ design, hero = false, expanded = false }: { design: Design; hero?: boolean; expanded?: boolean }) {
  const [internal, setInternal] = useState(false), [open, setOpen] = useState(false);
  useEffect(() => { if (!open) return; const handler = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); }; window.addEventListener("keydown", handler); return () => window.removeEventListener("keydown", handler); }, [open]);
  const url = design.assets[internal ? "internal.glb" : "model.glb"];
  return <div className={hero ? vtol.hero : ""}>
    <div className={vtol.view} data-testid={hero ? "overview-model" : undefined} data-view={internal ? "internal" : "exterior"}>
      {url ? <Viewer key={url} url={url} internal={internal} /> : <div className={styles.loading}>Geometry unavailable</div>}
      <div className={vtol.controls}><button aria-pressed={!internal} onClick={() => setInternal(false)}>Exterior</button><button aria-pressed={internal} onClick={() => setInternal(true)}>Internal layout</button></div>
      {!expanded && <button className={vtol.expand} aria-label={`Expand iteration ${design.iteration}`} onClick={() => setOpen(true)}><Maximize2 size={15} /></button>}
    </div>
    {open && <div className={vtol.modal} role="dialog" aria-modal="true" aria-label={`Iteration ${design.iteration}`} onClick={() => setOpen(false)}><div onClick={e => e.stopPropagation()}><Model design={design} expanded /><button className={vtol.close} onClick={() => setOpen(false)}>Close</button></div></div>}
  </div>;
}
function PowerCurve({ points }: { points: Point[] }) {
  if (!points.length) return null;
  const lo = Math.min(...points.map(p => p.speed_m_s)), hi = Math.max(...points.map(p => p.speed_m_s)), max = Math.max(...points.map(p => p.power_w));
  const coords = points.map(p => `${30+(p.speed_m_s-lo)/Math.max(1,hi-lo)*320},${110-p.power_w/max*90}`).join(" ");
  return <svg className={vtol.plot} viewBox="0 0 380 145" role="img" aria-label="Electrical cruise power versus airspeed"><path d="M30 15 V110 H355" fill="none" stroke="#c5cfbf" /><polyline points={coords} fill="none" stroke="#496b46" strokeWidth="2" /><text x="2" y="16">{max.toFixed(0)} W</text><text x="28" y="130">{lo.toFixed(1)} m/s</text><text x="300" y="130">{hi.toFixed(1)} m/s</text></svg>;
}
export default function VTOLGallery({ data }: { data: VTOLData }) {
  const best = data.designs.find(d => d._id === data.best_id), base = data.designs[0];
  if (!best) return <main className={styles.page}><h1>Da Vinci</h1><p>VTOL evaluation in progress.</p><a href="/gripper">Gripper study</a></main>;
  const max = Math.max(...data.designs.map(d => value(d,"range_km") || 0));
  return <main className={styles.page}>
    <header className={styles.header}><div><h1>Da Vinci <span>Recursive Improvement CAD Harness</span></h1><p>Lift-and-cruise VTOL · {data.designs.length} GPT-6 Astra iterations</p></div><span className={styles.material}>0.5 kg payload · 150 Wh battery</span></header>
    <section className={styles.overview} aria-label="Project overview"><Model design={best} hero /><div className={styles.overviewText}>
      <section><h2>Self-improvement methods</h2><p className={styles.methodIntro}>Optimize estimated range. Benchmark speed, payload and endurance under the same checks.</p>
        <div className={styles.method}><h3>1. Reflect and remember</h3><p>Review drag, energy, trim and structural margins. Retrieve earlier results and carry lessons into the next design.</p></div>
        <div className={styles.method}><h3>2. Create and reuse tools</h3><p>Generate a range-sensitivity utility, test it independently and execute it before later proposals.</p></div>
        <div className={styles.method}><h3>3. Evaluate and revise</h3><p>Change the fuselage, wing, tail and component layout. Keep the battery and mission payload fixed.</p></div><ResearchEvidence />
      </section>
      <section className={styles.atlas}><h2>MongoDB Atlas</h2><p><strong>Documents</strong> archive designs, evaluations and policies. <strong>Vector Search</strong> retrieves prior results. <strong>GridFS</strong> preserves CAD and source artifacts.</p></section>
      <details className={styles.disclosure}><summary>Agent harness setup and physics</summary><div className={styles.disclosureBody}>
        <h3>Independent evaluation</h3><p>Astra proposes CAD parameters. Separate containers build the assembly and verify its exported STEP against a trusted reference. AeroSandbox VLM evaluates lifting surfaces and trim; XFOIL polars estimate viscous drag. Measured UIUC propeller maps connect thrust to electrical power.</p>
        <p>Component masses determine balance, hover demand and wing loading. Tapered spars must stay inside the airfoil. Beam screens integrate their changing stiffness and check booms and payload support. The mission deducts 90 seconds hover and 40 seconds transition allowance, with 20% battery reserve.</p>
        <h3>Champion requirements</h3><p>At least 10% more range, positive improvement under combined adverse assumptions, finer-grid convergence, and at least 95% of baseline speed and payload capacity. Failures remain visible.</p>
        <p>This sequential study reuses Atlas memory and archives. Database Triggers drive the separate <a href="/harness">full workbench</a>. Recorded API accounting: ${data.spent_usd.toFixed(2)} of a $30 cap.</p>
        <p>The initial screening campaign was withdrawn after a spar-to-airfoil mismatch. This corrected campaign checks containment and material volume; the total cost includes the earlier calls. <a href="/studies/vtol-first-campaign-audit.json">Initial campaign audit</a>.</p><h3>Sources and measurement scope</h3><p><a href="https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html">UIUC experimental propeller data</a> · <a href="https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/vortex_lattice_method/">AeroSandbox VLM</a> · <a href="https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt">XFOIL</a></p>
        <p>Engineering estimates, not flight-test results. Hardware masses, motor efficiency and power limits are assumptions. No full-aircraft CFD, dynamic transition, rotor interference, flutter, fatigue or closed-loop control. Payload capacity is for a 10 km mission and is bounded by the fixed bay. Maximum speed is the highest supported passing sweep point; unsupported propeller conditions are not extrapolated. Range is total cruise distance, not radius. Propeller shapes are clearance/display surrogates; performance comes from the fixed measured maps. This campaign has no ablation isolating each self-improvement method.</p>
      </div></details>
    </div></section>
    <div className={styles.sectionHeading}><h2>All {data.designs.length} design iterations</h2><span>Estimated performance · same battery and payload</span></div>
    {!data.publishable && <p className={vtol.notice}>Study results — the complete champion validation gate has not passed.</p>}
    <section className={styles.progress} aria-label="Range progress"><div className={styles.progressSummary}><span className={styles.eyebrow}>BEST PASSING RANGE ESTIMATE</span><strong>{value(base,"range_km")?.toFixed(1)} <span>→</span> {value(best,"range_km")?.toFixed(1)} <small>km</small></strong><span className={styles.reduction}>{data.improvement_percent.toFixed(1)}% range improvement</span></div>
      <div className={`${styles.chart} ${vtol.rangeChart}`}>{data.designs.map(d => <a href={`#iteration-${d.iteration}`} key={d._id} className={`${styles.barColumn} ${d._id===best._id ? styles.bestBar : ""} ${d.evaluation.outcome!=="passed" ? styles.failedBar : ""}`}><span>{value(d,"range_km")?.toFixed(1) ?? "—"}</span><div style={{height:`${Math.max(6,(value(d,"range_km")||0)/max*58)}px`}}/><small>{String(d.iteration).padStart(2,"0")}</small></a>)}</div>
      <p className={styles.constraints}>Range-focused campaign<br/>Speed and payload protected<br/>Reserve: 20%</p></section>
    <section className={styles.grid} aria-label="Generated VTOL aircraft">{data.designs.map(d => {
      const ok=d.evaluation.outcome==="passed", isBest=d._id===best._id, n=d.evaluation.performance?.nominal;
      return <article id={`iteration-${d.iteration}`} key={d._id} data-testid="design-card" className={`${styles.card} ${isBest ? styles.bestCard : ""}`}>
        <div className={styles.cardHeader}><span className={styles.iteration}>{String(d.iteration).padStart(2,"0")}</span><h2>{d.title}</h2><span className={`${styles.badge} ${ok ? "" : styles.failed}`}>{isBest ? <><Check size={12}/>Best</> : !ok ? "Failed check" : d.iteration===1 ? "Baseline" : "Passed"}</span></div><Model design={d}/>
        <div className={styles.cardDetails}><p className={styles.description}>{d.parameters.span?.toFixed(2) ?? "—"} m span · {d.parameters.fuselage_length?.toFixed(2) ?? "—"} m body · {value(d,"mass_kg")?.toFixed(2) ?? "—"} kg</p>
          <dl className={styles.metrics}>{[["range_km","Range","km",1],["max_speed_m_s","Max speed","m/s",1],["payload_capacity_kg","Payload capacity","kg",2],["endurance_min","Endurance","min",1]].map(([key,label,unit,digits]) => <div key={key}><dt>{label} est.</dt><dd>{value(d,String(key))?.toFixed(Number(digits)) ?? "—"} <small>{unit}</small></dd></div>)}</dl>
          {!ok && <p className={vtol.notice}>{d.evaluation.violations.map(v=>v.code.toLowerCase().replaceAll("_"," ")).join(" · ")}</p>}
          <details className={vtol.evidence}><summary>Physics results and agent reflection</summary><p>{d.change}</p><p>{d.reflection.lesson}</p><p>{d.reflection.next_focus}</p>
            {n && <><div className={vtol.breakdown}><span>VTOL/transition: {n.overhead_wh.toFixed(1)} Wh</span><span>Reserve: {n.reserve_wh.toFixed(0)} Wh</span><span>Static margin: {(n.static_margin*100).toFixed(1)}%</span><span>Hover thrust reserve: {n.hover_thrust_ratio.toFixed(2)}×</span></div>
              {n.best && <p>Best-range drag: body {n.best.body_drag_n.toFixed(2)} N · induced {n.best.induced_drag_n.toFixed(2)} N · profile {n.best.profile_drag_n.toFixed(2)} N · hardware {n.best.hardware_drag_n.toFixed(2)} N. Consumption: {n.best.wh_km.toFixed(2)} Wh/km.</p>}
              {n.structure && <p>Wing screening: {(n.structure.wing.stress_pa/1e6).toFixed(1)} MPa stress · {(n.structure.wing.deflection_m*1000).toFixed(1)} mm deflection. Boom stress: {(n.structure.boom.stress_pa/1e6).toFixed(1)} MPa.</p>}<PowerCurve points={n.curve}/><p className={vtol.caption}>Electrical cruise power across supported airspeeds.</p>
              <p>Combined adverse range: {d.evaluation.performance?.scenarios.combined_adverse.range_km.toFixed(1)} km. {d.evaluation.performance?.scenarios.combined_adverse.violations.length ? "Fails scenario constraints." : "Passes scenario constraints."} Assumes 10% less usable battery energy, 20% more parasite drag and 10% more empty mass.</p></>}
              {data.validation?.validations[d._id] && <p>Finer-grid validation: {data.validation.validations[d._id].converged ? "converged within 3%" : "did not converge within 3%"}; {data.validation.validations[d._id].evaluation.outcome === "passed" ? "aircraft checks passed" : "aircraft checks failed"}.</p>}
          </details>
          <div className={styles.cardFooter}><span>{d.tool_id ? "Saved energy tool used" : "Initial aircraft exploration"}</span>{d.assets["model.step"] && <a href={d.assets["model.step"]} download><ArrowDownToLine size={13}/>STEP</a>}</div>
        </div></article>;
    })}</section><div className={styles.bottom}><a href="/gripper">Gripper study ↗</a><a href="/sensor">Sensor study ↗</a><a href="/harness">Full harness ↗</a></div>
  </main>;
}
