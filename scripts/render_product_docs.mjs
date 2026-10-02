import { readFile, readdir } from "node:fs/promises";
import { marked } from "marked";

export function documentationNavigation(sections) {
  return sections.map(section => `<section><h2>${section.title}</h2><ul>${section.items.map(item => `<li><a href="/docs/${item.slug}/">${item.title}</a></li>`).join("")}</ul></section>`).join("");
}
export const headingId = text => text.toLowerCase().replace(/<[^>]*>/g, "").replace(/[^\p{L}\p{N}\s-]/gu, "").trim().replace(/\s+/g, "-");
export function renderDocument(source, sections = []) {
  const renderer = new marked.Renderer();
  renderer.heading = function({tokens, depth, text}) {
    return `<h${depth} id="${headingId(text)}">${this.parser.parseInline(tokens)}</h${depth}>\n`;
  };
  return marked.parse(source.replace(/<!-- documentation-navigation -->[\s\S]*?<!-- \/documentation-navigation -->/, documentationNavigation(sections)), {renderer})
    .replace(/href="(?:\.\/)?([a-zA-Z0-9-]+)\.md(#[^"]*)?"/g, (_, slug, anchor = "") => `href="/docs/${slug === "README" ? "" : slug + "/"}${anchor}"`)
    .replace(/href="(?:\.\/)?([a-z-]+\.json)"/g, 'href="/docs/evidence/$1"');
}
export async function documents() {
  const sections = JSON.parse(await readFile("docs/product/navigation.json", "utf8"));
  const names = (await readdir("docs/product")).filter(n => n.endsWith(".md"));
  return Promise.all(names.map(async name => ({
    slug: name === "README.md" ? "index" : name.slice(0, -3),
    html: renderDocument(await readFile(`docs/product/${name}`, "utf8"), sections),
  })));
}
export const docStyle = `body{margin:0;background:#f4f4ee;color:#263a2f;font:15px/1.7 Arial,sans-serif}main{max-width:850px;margin:auto;padding:40px 24px}a{color:#46673e}h1{font-size:40px;line-height:1.15;font-weight:500;letter-spacing:-1px}h2{margin-top:36px;font-size:23px;font-weight:500}pre{background:#e6eadf;overflow:auto;padding:18px;font-size:12px;border-radius:4px}code{font-size:.9em}table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow:auto}th,td{text-align:left;padding:10px;border-bottom:1px solid #cbd4c2}blockquote{border-left:3px solid #a4b696;padding-left:20px}nav{font-size:13px;display:flex;justify-content:space-between;margin-bottom:35px}.lifecycle-flow{text-align:center;background:#e6eadf;border:1px solid #cbd4c2;border-radius:6px;padding:16px}.lifecycle-flow p{margin:8px}a:focus-visible,summary:focus-visible{outline:2px solid #a65d3b;outline-offset:3px}`;
