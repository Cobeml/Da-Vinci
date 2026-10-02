import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { notFound } from "next/navigation";
import { renderDocument } from "../../../../scripts/render_product_docs.mjs";
import s from "../../../../ui/components/workspace.module.css";
const folder = join(process.cwd(), "..", "docs", "product");
// Next CLI uses web/ as its process directory for server rendering.
function root() {
  try {
    readdirSync(folder);
    return folder;
  } catch {
    return join(process.cwd(), "docs", "product");
  }
}
export const dynamicParams = false;
export function generateStaticParams() {
  return readdirSync(root())
    .filter((n) => n.endsWith(".md") && n !== "README.md")
    .map((n) => ({ slug: n.slice(0, -3) }));
}
export default async function Doc({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  if (!generateStaticParams().some((p) => p.slug === slug)) notFound();
  const html = renderDocument(
    readFileSync(join(root(), slug + ".md"), "utf8"),
  );
  return (
    <main className={s.page}>
      <nav className={s.nav}>
        <a href="/docs">← Documentation</a>
        <a href="/demo">Object gallery demo →</a>
      </nav>
      <article
        className="product-guide"
        dangerouslySetInnerHTML={{
          __html: html,
        }}
      />
    </main>
  );
}
