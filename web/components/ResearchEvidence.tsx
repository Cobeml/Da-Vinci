import styles from "./SensorGallery.module.css";

export default function ResearchEvidence() {
  return <details className={styles.disclosure}>
            <summary>Research evidence</summary>
            <div className={styles.disclosureBody}>
              <p className={styles.evidence}><strong>Reflection and memory.</strong> <a href="https://arxiv.org/abs/2609.08832" target="_blank" rel="noopener noreferrer">Closing the Consistency Gap · 8 Sep 2026 ↗</a> reported <strong>+16 percentage points</strong> in AppWorld tasks succeeding on all five runs, using stored diagnostic guidelines with ReAct/GPT-4.1; <strong>+13 points</strong> on similar tasks.</p>
              <p className={styles.evidence}><strong>Reusable skills.</strong> <a href="https://arxiv.org/abs/2608.23417" target="_blank" rel="noopener noreferrer">SkillAlchemy · 24 Aug 2026 ↗</a> reported <strong>+19.9 percentage points</strong> pass rate over execution without skills across 87 SkillsBench tasks, by creating reusable skill packages from source material.</p>
              <p className={styles.evidence}><strong>Evaluation and revision.</strong> <a href="https://arxiv.org/abs/2609.26457" target="_blank" rel="noopener noreferrer">AIDE² · 22 Sep 2026 ↗</a> found <strong>7 successive agent improvements in 8 days</strong> by testing changes to its own code. Gains transferred to four held-out benchmarks.</p>
              <p className={styles.researchNote}>Recent preprints; results are from other tasks, not validation of this CAD harness or measurements of each method’s contribution here.</p>
            </div>
          </details>;
}
