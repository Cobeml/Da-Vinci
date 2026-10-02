import type { Metadata } from "next";
import RecordedModels, {type RecordedObject} from "../../components/RecordedModels";
import HarnessOverview from "../../components/HarnessOverview";
import s from "../../../ui/components/workspace.module.css";
import r from "../../components/RecordedStudy.module.css";
import sensor from "../../data/sensor-gallery.json";
import gripper from "../../data/gripper-gallery.json";
import vtol from "../../data/vtol-gallery.json";
import structural from "../../public/studies/structural/report.json";
import mechanism from "../../public/studies/mechanism/report.json";
export const metadata: Metadata = {title:"Da Vinci — recorded object gallery",description:"Interactive CAD studies and native structural/mechanism validation, with frozen tests and recorded evidence."};
export default function Page() {
  const native: RecordedObject[] = [structural, mechanism].map(data => {
    const final = data.iterations.filter(i=>i.accepted).at(-1)!;
    return {id:data.slug,name:data.name,href:`/${data.slug}`,previewUrl:final.assets["model.glb"],count:data.iterations.length,metric:data.slug === "structural" ? "0.013 mm deflection" : "30.59 g moving mass",evidence:"Native solver · scripted reasoning",description:"Accepted under stated tests · failures retained"};
  });
  const historical: RecordedObject[] = [
    {id:"sensor",name:"Sensor mount",data:sensor,metric:"mass_g",direction:"minimize"},
    {id:"gripper",name:"Parallel gripper",data:gripper,metric:"mass_g",direction:"minimize"},
    {id:"vtol",name:"Survey VTOL",data:vtol,metric:"range_km",direction:"maximize"},
  ].map(({id,name,data,metric,direction})=>{
    const passing = data.designs.filter(d=>d.evaluation.outcome === "passed");
    const value = (d:typeof passing[number]) => (d.evaluation.metrics as Record<string,{value:number;unit:string}>)[metric];
    const best = passing.reduce((a,b)=> (direction === "minimize" ? value(b).value < value(a).value : value(b).value > value(a).value) ? b : a);
    return {id,name,href:`/${id}`,previewUrl:"model_url" in best ? best.model_url : "assets" in best ? best.assets["model.glb"] : undefined,count:data.designs.length,metric:`${value(best).value.toFixed(2)} ${value(best).unit}`,evidence:"Historical model-driven study",description:"Best passing legacy design · engineering estimates"};
  });
  return <main className={s.page}>
    <nav className={s.nav}><a className={s.brand} href="/">Da Vinci<span>Recursive improvement CAD harness</span></a><a href="/docs">Documentation ↗</a></nav>
    <header className={s.header}><div><span className={s.eyebrow}>RECORDED WORKSPACE</span><h1>Objects</h1><p>Inspect generated geometry, design revisions and the evidence behind each result.</p></div><a className={s.textLink} href="/docs/quickstart/">Run your own workspace →</a></header>
    <HarnessOverview/>
    <div className={r.section}><h2>Native solver validation examples</h2><p>Actual CAD and solver execution through both drivers. Scripted proposals and deterministic managed fixtures test the workflow; they do not measure autonomous reasoning quality.</p></div>
    <RecordedModels objects={native} wide/>
    <div className={r.section}><h2>Historical model-driven studies</h2><p>Recorded model proposals and engineering screening estimates. These archives precede the current test-first lifecycle.</p></div>
    <RecordedModels objects={historical}/>
    <footer className={s.footer}><span>Read-only demo · no API calls</span><span>Evidence is limited to each study’s tests and assumptions.</span></footer>
  </main>;
}
