import { RecordedModel } from "./RecordedModels";
import s from "../../ui/components/workspace.module.css";
import r from "./RecordedStudy.module.css";
export type Quantity = {value:number;unit:string;numerical_error:number;uncertainty:number};
type TestResult = {test_id:string;status:string;reason:string|null;message?:string;metrics:Record<string,Quantity>};
type Iteration = {id:string;iteration:number;title:string;change:string;candidate_version:string;source_artifact:string;result_id:string;suite_id:string;runtime_id:string;execution_id:string;accepted:boolean;evidence_complete:boolean;objective_target_attained:boolean|null;duration_seconds:number;tests:TestResult[];assets:Record<string,string | undefined>;trajectory:number[][]};
export type Study = {version:number;slug:string;name:string;experiment_id:string;description:string;reasoning:string;suite_id:string;runtime:{image:string;solver:string;backend:string;cpu_cores:number};coverage:{complete:boolean;requirement_tests:Record<string,string[]>;uncovered_critical:string[]};assumptions:{description:string;source:string;applicability:string}[];tests:{id:string;required:boolean;applicability:string;criteria:{metric:string;operator:string;limit:number;unit:string}[];accuracy:unknown;fixed_inputs:unknown;load_cases:unknown;simulation:{fidelity:string;stage:string}}[];iterations:Iteration[];report_url:string;manifest_url:string;comparison_url:string};
const labels:Record<string,string> = {mass_g:"Mass",load_displacement_mm:"Load displacement",gauge_von_mises_mpa:"Mean gauge stress",tracking_error_m:"Final tracking error",settled_penetration_m:"Settled penetration",equilibrium_error_n:"Reaction imbalance",peak_actuation_n:"Peak actuator force"};
function number(value:number) { return value.toLocaleString("en-US",{maximumSignificantDigits:3}); }
function measurement(q:Quantity) {
  // Display resolution cannot suggest accuracy finer than the archived numerical error.
  if (q.numerical_error > 0 && Math.abs(q.value) < q.numerical_error) return `< ${number(q.numerical_error)} ${q.unit}`;
  const step = q.numerical_error > 0 ? 10 ** Math.floor(Math.log10(q.numerical_error)) : 0;
  const rounded = step ? Math.round(q.value / step)*step : q.value;
  return `${number(rounded)} ${q.unit}`;
}
function status(d:Iteration) {
  if(d.accepted && d.evidence_complete) return "Accepted under stated tests";
  const state = d.tests.find(t=>t.status !== "pass")?.status;
  return ({physical_failure:"Physical failure",invalid_setup:"Invalid setup",numerical_failure:"Numerical failure",unsupported_capability:"Unsupported capability",not_run:"Not run"} as Record<string,string>)[state || ""] || "Incomplete evidence";
}
function title(d:Iteration,index:number,total:number,mechanism:boolean) {
  if(mechanism && index === total-1) return "Pocketed carriage · repeated final check";
  return ({"bracket-base":"Perforated bracket","bracket-ribbed":"Ribbed bracket",solid:"Solid carriage",ambiguous:"Ambiguous body binding",misplaced:"Misplaced carriage",pocketed:"Pocketed carriage"} as Record<string,string>)[d.title] || d.title;
}
function Trajectory({initial,final}: {initial:Iteration;final:Iteration}) {
  const series = [initial.trajectory, final.trajectory];
  const ymin = Math.min(-5, ...series.flat().map(p=>p[1]))-2;
  const ymax = 35;
  const x = (t:number)=>50+t/2*550, y = (q:number)=>200-(q-ymin)/(ymax-ymin)*170;
  return <figure style={{margin:"22px 0"}}>
    <svg className={r.chart} viewBox="0 0 640 245" role="img" aria-label="Recorded lift trajectory: solid carriage falls; pocketed carriage reaches the 30 mm target">
      {[0,15,30].map(q=><g key={q}><line x1="50" x2="600" y1={y(q)} y2={y(q)} stroke="#ccd6c4"/><text x="8" y={y(q)+4}>{q}</text></g>)}
      <line x1="50" x2="600" y1={y(30)} y2={y(30)} stroke="#6b776a" strokeDasharray="5 5"/>
      {series.map((points,index)=><polyline key={index} fill="none" stroke={index ? "#345d49" : "#a65d3b"} strokeWidth="2.5" points={points.map(p=>`${x(p[0])},${y(p[1])}`).join(" ")}/>)}
      {[0,1,2].map(t=><text key={t} x={x(t)} y="220" textAnchor="middle">{t} s</text>)}<text x="12" y="17">Lift (mm)</text>
    </svg>
    <figcaption className={r.caption}>Recorded finest-step trajectory · orange: solid · green: pocketed · dashed: 30 mm target. Plot sampled for display; full CSVs are available below.</figcaption>
  </figure>;
}
export default function RecordedStudy({data}:{data:Study}) {
  const mechanism = data.slug === "mechanism";
  const final = data.iterations.filter(d=>d.accepted).at(-1)!;
  const first = data.iterations[0];
  const metricNames = Object.keys(final.tests[0].metrics);
  return <main className={s.page}>
    <nav className={s.nav}><a href="/demo">← Object gallery</a><a href="/docs">Documentation ↗</a><a href="https://github.com/Cobeml/Da-Vinci">GitHub ↗</a></nav>
    <header className={s.header}><div><span className={s.eyebrow}>NATIVE SOLVER VALIDATION · RECORDED</span><h1>{data.name}</h1><p>{data.runtime.solver} · {data.reasoning}</p></div></header>
    <section className={r.hero}>
      <div><RecordedModel url={final.assets["model.glb"]} label={`Final ${data.name.toLowerCase()}`}/></div>
      <div><span className={s.eyebrow}>SAME FROZEN ACCEPTANCE TESTS</span><h2>{mechanism ? "52.8% lower moving mass." : "Lower deflection. Higher mass."}</h2><p>{mechanism ? "A pocketed carriage reaches the 30 mm lift target under the same 0.4 N force cap. The solid carriage fails the motion requirement." : "Ribs reduce load displacement from 0.178 to 0.0129 mm under a fixed 20 N load. Mass rises from 18.30 to 22.97 g."}</p><p className={r.pass}>Final evidence complete · accepted under stated tests</p><p>{mechanism ? "Rigid-body motion and frictionless soft contact only. No structural strength or fatigue claim." : "Linear-elastic, small-deformation solid FEA. Stress is a predeclared volume mean gauge, not a peak-stress strength claim."}</p><a href={`/docs/${data.slug === "structural" ? "structural" : "mechanism"}-simulation/`}>Scope and reproduction commands →</a></div>
    </section>
    <div className={r.tableWrap}><table className={r.metrics}><caption>Baseline and final simulation results</caption><thead><tr><th>Quantity</th><th>Baseline</th><th>Final</th><th>Acceptance limit</th></tr></thead><tbody>{metricNames.map(key=>{
      const a=first.tests[0].metrics[key], b=final.tests[0].metrics[key];
      const criterion=data.tests.flatMap(t=>t.criteria).find(c=>c.metric === key);
      return <tr key={key}><td>{labels[key] || key}{mechanism && key === "mass_g" ? " (moving body)" : ""}</td><td>{measurement(a)}</td><td>{measurement(b)}</td><td>{criterion ? `${criterion.operator} ${number(criterion.limit)} ${criterion.unit}` : "Reported quantity"}</td></tr>;
    })}</tbody></table></div>
    <p className={r.caption}>Displayed values are rounded. Acceptance includes the frozen numerical-error and uncertainty rules; a nominal value alone is insufficient.</p>
    {mechanism && <Trajectory initial={first} final={final}/>}
    <details className={r.detail}><summary>Coverage, assumptions and final checks</summary><p>{Object.keys(data.coverage.requirement_tests).length} of {Object.keys(data.coverage.requirement_tests).length + data.coverage.uncovered_critical.length} declared critical requirements covered. {data.tests.filter(t=>t.required).length} required test(s). Final evidence completeness is independent of whether a design passes.</p>{data.tests.map(t=><div key={t.id}><p><strong>{t.id}</strong> · {t.simulation.fidelity.replaceAll("_"," ")} · {t.simulation.stage}<br/>{t.applicability}</p></div>)}{data.assumptions.map(a=><p key={a.description}>{a.description}<br/><small>Source: {a.source}</small></p>)}<p>Both routes execute native physics with deterministic/scripted proposals. This demonstrates lifecycle and adapter behavior, not autonomous reasoning or laboratory validation.</p><a href={data.comparison_url}>Both-driver evidence JSON ↗</a></details>
    <details className={r.detail}><summary>Frozen setup and numerical requirements</summary><pre style={{overflowX:"auto",fontSize:12}}>{JSON.stringify(data.tests.map(t=>({test:t.id,fixed_inputs:t.fixed_inputs,load_cases:t.load_cases,accuracy:t.accuracy})),null,2)}</pre></details>
    <details className={r.detail}><summary>Report and provenance</summary><p>Experiment <code>{data.experiment_id}</code><br/>Suite <code>{data.suite_id}</code><br/>Runtime <code>{data.runtime.image}</code></p><p>Curated copies retain source/result identities. Artifact checksums identify the preserved bytes; the original workspace archive is unchanged.</p><div className={r.downloads}><a href={data.report_url}>Recorded report JSON</a><a href={data.manifest_url}>Artifact checksum manifest</a></div></details>
    <div className={r.section}><h2>All {data.iterations.length} recorded evaluations</h2><p>Chronological order · failures and final rechecks retained</p></div>
    <section className={r.iterations}>{data.iterations.map((d,index)=><article className={r.iteration} key={d.result_id} data-testid="design-card">
      <span className={s.eyebrow}>{String(index+1).padStart(2,"0")} · {d.evidence_complete ? "Evidence complete" : "Evidence incomplete"}</span><h2>{title(d,index,data.iterations.length,mechanism)}</h2><p className={d.accepted ? r.pass : r.fail}>{status(d)}</p>
      {d.assets["model.glb"] ? <RecordedModel url={d.assets["model.glb"]} label={title(d,index,data.iterations.length,mechanism)}/> : <div className={r.empty}>No rendered geometry retained for this invalid setup. Inspect the recorded diagnostic.</div>}
      <p>{d.change}</p>
      {d.tests.map(t=><div key={t.test_id}>{t.message && <p>{t.message}</p>}<div className={r.tableWrap}><table className={r.metrics}><tbody>{Object.entries(t.metrics).map(([key,q])=><tr key={key}><th>{labels[key] || key}</th><td>{measurement(q)}</td></tr>)}</tbody></table></div></div>)}
      <details className={r.detail}><summary>Accuracy, outcomes and provenance</summary>{d.tests.map(t=><div key={t.test_id}><p>{t.test_id}: {t.status.replaceAll("_"," ")} · {t.reason || "No reason code"}</p>{Object.entries(t.metrics).map(([key,q])=><p key={key}>{labels[key] || key}: numerical error {number(q.numerical_error)} {q.unit}; uncertainty allowance {number(q.uncertainty)} {q.unit}.</p>)}</div>)}<p>Objective target: {d.objective_target_attained === null ? "not specified" : d.objective_target_attained ? "attained" : "not attained"}. Execution: {number(d.duration_seconds)} s.</p><p>Candidate <code>{d.candidate_version}</code><br/>Source <code>{d.source_artifact}</code><br/>Result <code>{d.result_id}</code></p></details>
      <div className={r.downloads}>{Object.entries(d.assets).filter(([key])=>["model.step","model.glb"].includes(key)).map(([key,url])=><a key={key} href={url} download>{key === "model.step" ? "Download STEP" : "Download GLB"}</a>)}</div>
      <details className={r.detail}><summary>Simulation evidence files</summary><div className={r.downloads}>{Object.entries(d.assets).filter(([key])=>!["model.step","model.glb"].includes(key)).map(([key,url])=><a key={key} href={url}>{key.split("/").at(-1)}</a>)}</div></details>
    </article>)}</section>
    <footer className={s.footer}><span>Read-only demo · no API calls</span><span>Native simulation evidence · scripted reasoning</span></footer>
  </main>;
}
