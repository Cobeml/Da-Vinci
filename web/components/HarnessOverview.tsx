import styles from "./RecordedStudy.module.css";
import ResearchEvidence from "./ResearchEvidence";
export default function HarnessOverview() {
  return <section className={styles.overview} aria-label="How the harness works">
    <p className={styles.flow}>Define requirements <span>→</span> Verify and freeze tests <span>→</span> Generate CAD <span>→</span> Independently evaluate <span>→</span> Reflect and revise <span>→</span> Preserve evidence</p>
    <div className={styles.disclosures}>
      <details><summary>Agent workflows</summary><p>An external coding agent supplies reasoning through the CLI/API without a Da Vinci model key. The built-in agent takes a description and server-side credentials. Both use the same lifecycle, frozen tests and local execution.</p><p>Automatic new-test authoring currently supports rectangular cantilever screening. The bracket and slider below use authored tests and scripted reasoning. <a href="/docs/product-journeys/">User journeys →</a></p></details>
      <details><summary>Self-improvement methods</summary><p>Reflect on independent results, retrieve scoped experience and reuse tested tools. Lessons remain hypotheses until supported by evidence. Tools have independent checks, version pinning and rollback. Model weights and frozen acceptance limits stay fixed.</p><p><a href="/docs/memory/">Memory</a> · <a href="/docs/tool-learning/">Tool learning</a> · <a href="/docs/architecture/">Harness setup</a></p></details>
      <details><summary>Storage and MongoDB Atlas</summary><p>SQLite and local artifacts are the default. Atlas documents retain experiments and experience; GridFS stores checksummed artifacts. Explicitly configured Vector Search supplements scoped lexical retrieval. Embeddings are disabled by default and independent of the generation model.</p><p>Database Triggers belong to the historical hackathon workbench; the installed product uses its own worker. <a href="/docs/atlas/">MongoDB Atlas for Scalable Model Improvement →</a></p></details>
      <details><summary>Evidence and limits</summary><p>Simulation results apply to the frozen tests and documented solver scope. Execution completion alone does not establish acceptance. The held-out memory benchmark has not demonstrated design improvement and includes misleading retrievals. Measurement and calibration examples use synthetic fixtures; no laboratory data is claimed.</p><p><a href="/docs/capability-matrix/">Capability matrix</a> · <a href="/docs/methodology/">Benchmark evidence</a> · <a href="/docs/measurements/">Measurements and calibration</a></p></details>
    </div>
    <ResearchEvidence/>
  </section>;
}
