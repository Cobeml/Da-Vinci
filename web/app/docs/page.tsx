import s from "../../../ui/components/workspace.module.css";
const base = "/docs/";
export default function Docs() {
  return (
    <main className={s.page}>
      <nav className={s.nav}>
        <a className={s.brand} href="/demo">
          Da Vinci<span>CAD workspace</span>
        </a>
        <a href="/demo">Object gallery demo →</a>
      </nav>
      <header className={s.header}>
        <div>
          <span className={s.eyebrow}>
            PYTHON PACKAGE · LOCALHOST INTERFACE
          </span>
          <h1>Run your own workspace.</h1>
          <p>
            Define a task in YAML. Inspect generated models and measured
            results. Continue from an earlier design.
          </p>
        </div>
      </header>
      <section className={s.overview}>
        <div>
          <h2>Get started</h2>
          <p>
            The MVP runs on Python 3.11, Linux or WSL2, Git, and Docker. Install
            the wheel using the linked guide; PyPI publication is pending.
          </p>
          <pre>
            {
              "davinci init my-project --template sensor\ncd my-project\ndavinci setup --template sensor\ndavinci doctor\ndavinci serve"
            }
          </pre>
          <p>
            Set OPENAI_API_KEY in your environment or workspace .env. Local
            storage works without MongoDB Atlas.
          </p>
          <a href={base + "quickstart/"}>Installation guide ↗</a>
        </div>
        <div>
          <h2>Guides</h2>
          {[
            ["configuration.md", "YAML and workspace settings"],
            ["workspace.md", "Live runs and continuation"],
            ["custom-tasks.md", "Custom Python tasks and coding-agent prompt"],
            [
              "architecture.md",
              "Reflection, memory, tools, and independent evaluation",
            ],
            ["atlas.md", "Optional MongoDB Atlas"],
            ["development.md", "Development and release"],
          ].map(([file, title]) => (
            <p key={file}>
              <a href={base + file.replace(".md", "/")}>{title} ↗</a>
            </p>
          ))}
        </div>
      </section>
      <p className={s.muted}>
        CadQuery geometry and physics estimates are evaluated against the
        selected task contract. Results depend on its assumptions and fidelity.
      </p>
    </main>
  );
}
