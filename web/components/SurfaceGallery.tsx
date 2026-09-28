"use client";
import dynamic from "next/dynamic";
import { useEffect, useRef, useState } from "react";
import styles from "./SensorGallery.module.css";
import view from "./VTOLGallery.module.css";
import css from "./SurfaceGallery.module.css";

const Viewer = dynamic(() => import("./VTOLViewer"), { ssr: false });
type Evaluation = { outcome: string; metrics: Record<string, {value:number;unit:string}|undefined>; violations: {code:string;message:string}[]; performance?: {nominal:{best:{alpha_deg:number;elevator_deg:number;drag_n:number;wh_km:number}|null};scenarios:Record<string,{range_km:number;violations:string[]}>;direct_audit?:{min_confidence?:number;surrogate_errors?:Record<string,number>}|null} };
type Section = {upper_weights:number[];lower_weights:number[];leading_edge_weight?:number;TE_thickness?:number};
type Design = {_id:string;arm:string;iteration:number;title:string;change:string;geometry:{dimensions:Record<string,number>;root:Section;tip:Section};evaluation:Evaluation;assets:Record<string,string|undefined>;reflection:{lesson:string;next_focus:string};tool_calls:number;tool_failures:number;tool_seconds:number;numerical_evaluations?:number};
type Validation = {evaluation:Evaluation;converged:boolean;relative_range_change:number|null;section_crosscheck?:{passed:boolean}};
export type SurfaceData = {study_id:string;status:string;designs:Design[];validation:Record<string,Validation>;publishable:boolean;best_id:string|null;spent_usd:number;budget_usd:number};
const label = (arm:string) => arm === "control" ? "Dimensional controls" : "CST + surface tools";
const score = (d:Design,key="range_km") => d.evaluation.metrics[key]?.value ?? 0;

function Model({design,hero=false}:{design:Design;hero?:boolean}) {
  const [internal,setInternal] = useState(false), [visible,setVisible] = useState(hero);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!ref.current) return; const observer=new IntersectionObserver(([entry])=>setVisible(entry.isIntersecting),{rootMargin:"150px"});observer.observe(ref.current);return ()=>observer.disconnect(); },[]);
  const url=design.assets[internal?"internal.glb":"model.glb"];
  return <div ref={ref} className={hero?view.hero:""}><div className={view.view} data-testid={hero?"surface-overview":"surface-model"} data-view={internal?"internal":"exterior"}>
    {url && visible ? <Viewer key={url} url={url} internal={internal}/> : <div className={styles.loading}>{url?"3D model":"No valid geometry"}</div>}
    <div className={view.controls}><button aria-pressed={!internal} onClick={()=>setInternal(false)}>Exterior</button>{design.assets["internal.glb"]&&<button aria-pressed={internal} onClick={()=>setInternal(true)}>Internal layout</button>}</div>
  </div></div>;
}

function SectionPlot({design,baseline}:{design:Design;baseline:Design}) {
  const path=(section:Section)=>{
    const choose=[1,7,21,35,35,21,7,1];
    const surface=(upper:boolean)=>Array.from({length:81},(_,i)=>{
      const x=(1-Math.cos(Math.PI*i/80))/2;
      const weights=upper?section.upper_weights:section.lower_weights;
      const shape=weights.reduce((sum,w,j)=>sum+w*choose[j]*x**j*(1-x)**(7-j),0);
      const y=Math.sqrt(x)*(1-x)*shape+(upper?1:-1)*x*(section.TE_thickness??0)/2+(section.leading_edge_weight??0)*x*(1-x)**8.5;
      return `${20+300*x},${55-300*y}`;
    });
    return [...surface(true),...surface(false).reverse()].join(" ");
  };
  return <><svg viewBox="0 0 340 95" role="img" aria-label="Baseline, root and tip airfoil comparison" className={css.sections}>
    <polyline points={path(baseline.geometry.root)} fill="none" stroke="#9a9f97" strokeWidth="1.5" strokeDasharray="4 3"/>
    <polyline points={path(design.geometry.root)} fill="none" stroke="#496b46" strokeWidth="2"/>
    <polyline points={path(design.geometry.tip)} fill="none" stroke="#5983a2" strokeWidth="1.5" strokeDasharray="2 3"/>
  </svg><p>Same normalized chord · gray baseline · green root · blue tip</p></>;
}

function Progress({designs}:{designs:Design[]}) {
  const max=Math.max(1,...designs.map(d=>score(d)));
  return <div className={css.progress} aria-label="Range progress by experimental arm">{["control","surface_tools"].map(arm=>{
    const rows=designs.filter(d=>d.arm===arm);
    return <section key={arm}><h3>{label(arm)}</h3><div className={css.bars}>{rows.map(d=><a key={d._id} href={`#${d._id}`} className={d.evaluation.outcome!=="passed"?css.failed:""}><span>{score(d)?score(d).toFixed(1):"—"}</span><i style={{height:`${Math.max(3,score(d)/max*85)}px`}}/><small>{d.iteration}</small></a>)}</div></section>;
  })}</div>;
}

export default function SurfaceGallery({data}:{data:SurfaceData}) {
  const [arm,setArm]=useState("all");
  const passing=data.designs.filter(d=>d.evaluation.outcome==="passed");
  const best=data.designs.find(d=>d._id===data.best_id) ?? [...passing].sort((a,b)=>score(b)-score(a))[0] ?? data.designs[0];
  const rows=data.designs.filter(d=>arm==="all"||d.arm===arm);
  const base=data.designs.find(d=>d.arm==="control"&&d.iteration===1);
  const control=[...passing].filter(d=>d.arm==="control").sort((a,b)=>score(b)-score(a))[0];
  const treatment=[...passing].filter(d=>d.arm==="surface_tools").sort((a,b)=>score(b)-score(a))[0];
  const verified=(arm:string)=>data.designs.filter(d=>d.arm===arm&&data.validation[d._id]?.converged).sort((a,b)=>(data.validation[b._id].evaluation.metrics.range_km?.value??0)-(data.validation[a._id].evaluation.metrics.range_km?.value??0))[0];
  const hasValidation=Object.keys(data.validation).length>0;
  const summary=hasValidation ? [["Verified baseline",base&&data.validation[base._id]?.converged?base:undefined],["Best verified dimensional",verified("control")],["Best verified surface tools",verified("surface_tools")]] as const : [["Screening baseline",base],["Best dimensional screen",control],["Best surface-tool screen",treatment]] as const;
  return <main className={styles.page}>
    <header className={styles.header}><div><h1>Da Vinci <span>Recursive Improvement CAD Harness</span></h1><p>Streamlined VTOL · matched geometry-tool experiment</p></div><span className={styles.material}>0.5 kg payload · 150 Wh battery</span></header>
    {best && <section className={styles.overview} aria-label="Project overview"><Model design={best} hero/><div className={styles.overviewText}>
      <section><h2>Self-improvement methods</h2>
        <div className={styles.method}><h3>1. Change the surface</h3><p>Generate CST airfoils and smooth three-section wings. Edit a hollow fuselage and its fairings.</p></div>
        <div className={styles.method}><h3>2. Use engineering tools</h3><p>Compare section lift, drag and pitching moment. Run constrained airfoil optimization before submitting CAD.</p></div>
        <div className={styles.method}><h3>3. Reflect and retry</h3><p>Use evaluated range, trim and structural failures to guide the next design. Keep each experiment’s memory separate.</p></div>
      </section>
      <section className={styles.atlas}><h2>MongoDB Atlas</h2><p><strong>Documents</strong> archive geometry, tool calls and policies. <strong>Vector Search</strong> retrieves previous results within each arm. <strong>GridFS</strong> stores CAD artifacts.</p></section>
      <details className={styles.disclosure}><summary>Agent harness and comparison method</summary><div className={styles.disclosureBody}>
        <p>Both arms start from the same enclosed VTOL and use the same model, mission and evaluator. The control edits existing dimensions. The surface arm also edits CST coefficients and wing stations, and can invoke a numerical section optimizer.</p>
        <p>Each proposal has up to six tool rounds. Invalid edits return constraint errors. Separate network-isolated containers build STEP geometry and evaluate it. Source, geometry and evaluator versions are archived. The scoring code is frozen during the campaign.</p>
        <p>A three-task pilot checks editing, lofting and error recovery. The campaign permits up to 12 designs per arm, including the shared baseline. More numerical optimization work is available to the surface arm; this compares the complete tool package, not identical compute.</p>
        <p>Recorded API accounting: ${data.spent_usd.toFixed(2)} / ${data.budget_usd}. Stage: {data.status.replaceAll("_"," ")}. Triggers drive the separate <a href="/harness">full harness</a>; this study uses a resumable sequential runner.</p>
      </div></details>
      <details className={styles.disclosure}><summary>Research, physics and validation limits</summary><div className={styles.disclosureBody}>
        <p><a href="https://www.iisci.net/zh/article/doi/10.16356/j.2097-6771.2026.04.008/">August 2026: natural-language-driven airfoil design</a> describes LLM/CST workflows including long-endurance UAV design. Its accessible abstract supports feasibility; it does not establish a transferable improvement percentage.</p>
        <p><a href="https://github.com/peterdsharpe/NeuralFoil">NeuralFoil</a> supplies fast lift, drag and moment predictions. Its confidence output is a screening signal, not a calibrated probability of physical correctness. <a href="https://aerosandbox.readthedocs.io/en/master/autoapi/aerosandbox/aerodynamics/aero_3D/nonlinear_lifting_line/">AeroSandbox nonlinear lifting-line</a> checks finalists. <a href="https://web.mit.edu/drela/Public/web/xfoil/xfoil_doc.txt">XFOIL</a> provides section consistency checks, not independent experimental validation.</p>
        <p>Engineering estimates, not flight measurements. The evaluator includes geometry-dependent section aerodynamics, trim, conservative wetted-area body drag, structural screening and measured <a href="https://m-selig.ae.illinois.edu/props/volume-4/propDB-volume-4.html">UIUC propeller maps</a>. It does not resolve body separation, wing/body interference, rotor interaction, dynamic transition, flutter or joint failure. Fairings receive no assumed interference-drag discount.</p>
        <p>Promotion requires at least 5% more verified range than both the common baseline and control, at least 95% of baseline speed and payload, an adverse-case advantage, section cross-checks, and range convergence within 2%. Earlier VTOL results use a different evaluator and are not direct controls.</p>
      </div></details>
    </div></section>}
    <div className={styles.sectionHeading}><h2>Design progress</h2><span>Screening range · km · green passed · brown failed</span></div>
    <p className={view.notice}>{data.publishable?"The new-tool design passed the comparison and validation gates.":"Experiment results — no verified new-tool winner has passed all promotion gates."}</p>
    {!data.designs.length && <p>Preparing and validating the common baseline.</p>}
    {base && <dl className={css.summary} aria-label={hasValidation?"Verified range comparison":"Screening range comparison"}>{summary.map(([name,d])=><div key={name}><dt>{name}</dt><dd>{d?(hasValidation?data.validation[d._id].evaluation.metrics.range_km?.value??0:score(d)).toFixed(1):"—"} <small>km est.</small></dd></div>)}</dl>}
    <Progress designs={data.designs}/>
    <div className={css.filters} aria-label="Experiment filter">{["all","control","surface_tools"].map(a=><button key={a} aria-pressed={arm===a} onClick={()=>setArm(a)}>{a==="all"?"Both arms":label(a)}</button>)}</div>
    <section className={styles.grid} aria-label="Generated streamlined VTOL designs">{rows.map(d=>{
      const validation=data.validation[d._id];const ok=d.evaluation.outcome==="passed";
      return <article className={styles.card} key={d._id} id={d._id} data-testid="surface-card">
        <div className={styles.cardHeader}><span className={styles.iteration}>{String(d.iteration).padStart(2,"0")}</span><h2>{d.title}</h2><span className={`${styles.badge} ${!ok?styles.failed:""}`}>{d._id===data.best_id?"Validated winner":ok?"Screen passed":"Failed check"}</span></div>
        <Model design={d}/><div className={styles.cardDetails}><p className={styles.description}>{label(d.arm)} · {d.geometry.dimensions.span.toFixed(2)} m span</p>
          <dl className={styles.metrics}>{[["range_km","Range","km",1],["max_speed_m_s","Max speed","m/s",1],["payload_capacity_kg","Payload capacity","kg",2],["endurance_min","Endurance","min",1],["mass_kg","Mass","kg",2],["hover_power_w","Hover power","W",0]].map(([key,name,unit,digits])=><div key={key}><dt>{name} est.</dt><dd>{d.evaluation.metrics[String(key)]?.value.toFixed(Number(digits))??"—"} <small>{unit}</small></dd></div>)}</dl>
          {!ok && <p className={view.notice}>{d.evaluation.violations.map(v=>v.code.toLowerCase().replaceAll("_"," ")).join(" · ")}</p>}
          <details className={view.evidence}><summary>Changes, tools and validation</summary><p>{d.change}</p><p>{d.reflection.lesson}</p><p>Next: {d.reflection.next_focus}</p><p>{d.tool_calls} tool calls · {d.tool_failures} returned errors · {d.tool_seconds.toFixed(0)} seconds in tools · {d.numerical_evaluations??0} section-optimizer evaluations</p>
            {d.evaluation.performance?.nominal.best && <p>Trim: {d.evaluation.performance.nominal.best.alpha_deg.toFixed(2)}° angle of attack · {d.evaluation.performance.nominal.best.elevator_deg.toFixed(2)}° tail adjustment. Consumption: {d.evaluation.performance.nominal.best.wh_km.toFixed(2)} Wh/km.</p>}
            {validation && <p>Nonlinear finalist check: {validation.converged?"passed":"not passed"}. Range: {validation.evaluation.metrics.range_km?.value.toFixed(1)??"unsupported"} km. Refinement change: {validation.relative_range_change===null?"unavailable":(100*validation.relative_range_change).toFixed(2)+"%"}. XFOIL consistency: {validation.section_crosscheck?.passed?"passed":"not passed"}.</p>}
          </details>{base && <details className={view.evidence}><summary>Airfoil sections</summary><SectionPlot design={d} baseline={base}/></details>}<div className={styles.cardFooter}><span>{d.iteration===1?"Shared baseline":"Agent-generated revision"}</span>{d.assets["model.step"]&&<a href={d.assets["model.step"]} download>Download STEP</a>}</div>
        </div></article>;
    })}</section><div className={styles.bottom}><a href="/vtol">Previous VTOL study ↗</a><a href="/gripper">Gripper study ↗</a><a href="/sensor">Sensor study ↗</a><a href="/harness">Full harness ↗</a></div>
  </main>;
}
