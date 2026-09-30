import type { Metadata } from "next";
import Landing from "../components/Landing";
import sensor from "../data/sensor-gallery.json";

export const metadata: Metadata = {
  title: "Da Vinci — Recursive Improvement CAD harness",
  description:
    "A recursive improvement CAD harness. Explore the interactive demos and documentation.",
};

export default function Page() {
  const best = sensor.designs
    .filter((design) => design.evaluation.outcome === "passed")
    .reduce((a, b) =>
      a.evaluation.metrics.mass_g.value < b.evaluation.metrics.mass_g.value
        ? a
        : b,
    );
  return <Landing modelUrl={best.model_url} />;
}
