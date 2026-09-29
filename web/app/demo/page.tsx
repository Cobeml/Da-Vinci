import type { Metadata } from "next";
import Gallery from "../../../ui/components/Gallery";
import type { ObjectCard, Run, Design } from "../../../ui/components/types";
import styles from "../../../ui/components/workspace.module.css";
import sensor from "../../data/sensor-gallery.json";
import gripper from "../../data/gripper-gallery.json";
import vtol from "../../data/vtol-gallery.json";
export const metadata: Metadata = {
  title: "Da Vinci — object gallery demo",
  description: "Recorded sensor mount, gripper, and VTOL optimization runs.",
};
export default function Page() {
  const cards = [
    {
      id: "sensor",
      name: "Sensor mount",
      data: sensor,
      metric: "mass_g",
      direction: "minimize",
    },
    {
      id: "gripper",
      name: "Parallel gripper",
      data: gripper,
      metric: "mass_g",
      direction: "minimize",
    },
    {
      id: "vtol",
      name: "Survey VTOL",
      data: vtol,
      metric: "range_km",
      direction: "maximize",
    },
  ].map(({ id, name, data, metric, direction }) => {
    const passing = data.designs.filter(
      (d) => d.evaluation.outcome === "passed",
    );
    const best = passing.reduce((a, b) => {
      const av = (a.evaluation.metrics as Record<string, { value: number }>)[
          metric
        ].value,
        bv = (b.evaluation.metrics as Record<string, { value: number }>)[metric]
          .value;
      return (direction === "minimize" ? bv < av : bv > av) ? b : a;
    });
    const previewUrl =
      "model_url" in best
        ? best.model_url
        : "assets" in best
          ? best.assets["model.glb"]
          : undefined;
    return {
      _id: id,
      name,
      template: id,
      iteration_count: data.designs.length,
      href: `/${id}`,
      previewUrl,
      preview: {
        _id: best._id,
        run_id: data.study_id,
        iteration: best.iteration,
        title: best.title,
        change: best.change,
        parameters: best.parameters,
        source: "",
        artifacts: {},
        evaluation: best.evaluation,
      } as Design,
      run: {
        status: "completed",
        config: { objective: { metric, direction } },
      } as Run,
    } as ObjectCard;
  });
  return (
    <main className={styles.page}>
      <nav className={styles.nav}>
        <a className={styles.brand} href="/">
          Da Vinci<span>Recursive improvement CAD harness</span>
        </a>
        <a href="/docs">Documentation ↗</a>
      </nav>
      <header className={styles.header}>
        <div>
          <span className={styles.eyebrow}>RECORDED WORKSPACE</span>
          <h1>Objects</h1>
          <p>
            Three engineering tasks. Each object contains its generated designs
            and measured results.
          </p>
        </div>
        <a className={styles.textLink} href="/docs">
          Run your own workspace →
        </a>
      </header>
      <Gallery objects={cards} recorded />
      <footer className={styles.footer}>
        <span>Read-only demo · no API calls</span>
        <span>Performance values are engineering estimates.</span>
      </footer>
    </main>
  );
}
