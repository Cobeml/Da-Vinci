import s from "../../../ui/components/workspace.module.css";
import sections from "../../../docs/product/navigation.json";
export default function Docs() {
  return <main className={s.page}>
    <nav className={s.nav}><a className={s.brand} href="/">Da Vinci<span>Recursive improvement CAD harness</span></a><a href="/demo">Object gallery demo →</a></nav>
    <header className={s.header}><div><span className={s.eyebrow}>PYTHON PACKAGE · LOCALHOST INTERFACE</span><h1>Run your own workspace.</h1><p>Define and verify tests, iterate on CAD, and inspect the evidence. Use your coding agent or the built-in agent.</p></div></header>
    <section className={s.overview}>
      <div><h2>Install from source</h2><p>Python 3.11, Linux or WSL2, Git and Docker. Building the interface requires Node.js 22 and uv. PyPI publication is pending.</p><pre>{"git clone https://github.com/Cobeml/Da-Vinci.git\ncd Da-Vinci"}</pre><p><a href="/docs/quickstart/">Installation guide ↗</a> · <a href="https://github.com/Cobeml/Da-Vinci">GitHub ↗</a></p></div>
      <div><h2>Choose your agent</h2><p><a href="/docs/external-agents/"><strong>External coding agent →</strong></a><br/>Your agent supplies reasoning and CAD through the public CLI/API. Da Vinci runs locally without a model key or cloud database.</p><p><a href="/docs/managed-requests/"><strong>Built-in agent →</strong></a><br/>Start with a description and server-side model credentials. Automatic test authoring currently supports rectangular cantilever screening.</p><p><a href="/docs/custom-tasks/">Advanced YAML / custom tasks →</a></p></div>
    </section>
    <div className="docs-navigation">{sections.filter(section => section.title !== "Technical records").map(section => <section key={section.title}><h2>{section.title}</h2><ul>{section.items.map(item => <li key={item.slug}><a href={`/docs/${item.slug}/`}>{item.title} ↗</a></li>)}</ul></section>)}</div>
    <details className="docs-records"><summary>Technical records and historical validation</summary><ul>{sections.at(-1)!.items.map(item => <li key={item.slug}><a href={`/docs/${item.slug}/`}>{item.title} ↗</a></li>)}</ul></details>
    <p className={s.muted}>Acceptance is limited to the frozen tests and adapter scope. Native simulation, scripted reasoning and synthetic measurement fixtures are identified separately in the evidence.</p>
  </main>;
}
