"use client";
import dynamic from "next/dynamic";
import s from "../../ui/components/workspace.module.css";
const Model = dynamic(() => import("../../ui/components/ModelViewer"), {ssr:false});
export { Model as RecordedModel };
export type RecordedObject = {
  id: string; name: string; href: string; previewUrl?: string; count: number;
  metric: string; evidence: string; description: string;
};
export default function RecordedModels({objects}: {objects: RecordedObject[]}) {
  return <section className={s.grid} aria-label="Object gallery">{objects.map(o => <article className={s.card} key={o.id} data-testid="object-card">
    <div className={s.cardHeading}><span className={s.eyebrow}>{o.evidence}</span></div>
    <Model url={o.previewUrl} label={o.name}/>
    <div className={s.cardBody}><h2><a href={o.href}>{o.name} ↗</a></h2><div className={s.cardStats}><span>{o.count} recorded evaluations</span><strong>{o.metric}</strong></div><p>{o.description}</p><a className={s.textLink} href={o.href}>View iterations →</a></div>
  </article>)}</section>;
}
