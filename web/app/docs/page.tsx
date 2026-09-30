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
            The MVP runs on Python 3.11, Linux or WSL2, Git, and Docker. PyPI
            publication is pending. Clone the repository to install from source;
            building the interface also requires Node.js 22 and uv.
          </p>
          <pre>{"git clone https://github.com/Cobeml/Da-Vinci.git\ncd Da-Vinci"}</pre>
          <p>
            <a href="https://github.com/Cobeml/Da-Vinci">GitHub repository ↗</a>
            {" · "}
            <a href={base + "quickstart/"}>Installation guide ↗</a>
          </p>
          <p>Follow the installation guide, then create and start a workspace:</p>
          <pre>
            {
              "davinci init my-project --template sensor\ncd my-project\ndavinci setup --template sensor\ndavinci doctor\ndavinci serve"
            }
          </pre>
          <p>
            Set OPENAI_API_KEY in your environment or workspace .env. Local
            storage works without MongoDB Atlas.
          </p>
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
