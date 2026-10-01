"use client";
import dynamic from "next/dynamic";
import type { ObjectCard } from "./types";
import { artifactUrl } from "./types";
import s from "./workspace.module.css";
const Model = dynamic(() => import("./ModelViewer"), { ssr: false });
export default function Gallery({
  objects,
  recorded = false,
}: {
  objects: ObjectCard[];
  recorded?: boolean;
}) {
  return (
    <section className={s.grid} aria-label="Object gallery">
      {objects.map((o) => {
        const m = o.run?.config.objective.metric,
          metric = m ? o.preview?.evaluation?.metrics[m] : null;
        return (
          <article className={s.card} key={o._id} data-testid="object-card">
            <div className={s.cardHeading}>
              <span className={s.eyebrow}>{o.run?.driver || o.template}</span>
              <span className={s.badge}>
                {recorded ? "Recorded run" : o.run?.status || "Ready"}
              </span>
            </div>
            <Model
              url={
                o.previewUrl ||
                (o.preview?.artifacts["model.glb"]
                  ? artifactUrl(o.preview.artifacts["model.glb"])
                  : undefined)
              }
              label={o.name}
            />
            <div className={s.cardBody}>
              <h2>
                <a href={o.href || `/object/?id=${encodeURIComponent(o._id)}`}>
                  {o.name} <span aria-hidden>↗</span>
                </a>
              </h2>
              <div className={s.cardStats}>
                <span>{o.iteration_count} designs</span>
                {metric && (
                  <strong>
                    {metric.value.toFixed(2)} <small>{metric.unit}</small>
                  </strong>
                )}
              </div>
              <p>
                {o.improvement_percent != null
                  ? `${o.improvement_percent.toFixed(1)}% improvement · `
                  : ""}
                {o.run?.experiment?.report &&
                !o.run.experiment.report.accepted_candidate_ids.length
                  ? "No design accepted in final report"
                  : o.preview?.evaluation?.outcome === "passed"
                    ? "Best passing legacy design"
                    : o.preview?.evaluation?.outcome ===
                        "accepted_under_stated_tests"
                      ? "Accepted under stated tests"
                      : "Latest design · acceptance not established"}{" "}
                · engineering estimates
              </p>
              <a
                className={s.textLink}
                href={o.href || `/object/?id=${encodeURIComponent(o._id)}`}
              >
                View iterations →
              </a>
            </div>
          </article>
        );
      })}
    </section>
  );
}
