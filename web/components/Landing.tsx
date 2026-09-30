"use client";

import dynamic from "next/dynamic";
import styles from "./Landing.module.css";

const Viewer = dynamic(() => import("./SensorViewer"), { ssr: false });

export default function Landing({ modelUrl }: { modelUrl: string }) {
  return (
    <main className={styles.page}>
      <section className={styles.identity}>
        <span className={styles.logo} role="img" aria-label="Da Vinci logo">
          d<span>v</span>
        </span>
        <h1>Da Vinci</h1>
        <p>Recursive Improvement CAD harness</p>
        <nav className={styles.actions} aria-label="Explore Da Vinci">
          <a className={styles.primary} href="/demo">
            Demo <span aria-hidden="true">↗</span>
          </a>
          <a className={styles.secondary} href="/docs">
            Docs <span aria-hidden="true">↗</span>
          </a>
        </nav>
      </section>
      <div
        className={styles.model}
        data-testid="overview-model"
        role="group"
        aria-label="Interactive drone with sensor mount"
      >
        <Viewer url={modelUrl} mounted reset={0} />
      </div>
    </main>
  );
}
