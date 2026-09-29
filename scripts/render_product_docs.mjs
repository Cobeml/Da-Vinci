import { readFile, readdir } from "node:fs/promises";
import { marked } from "marked";
export async function documents() {
  const names = (await readdir("docs/product")).filter((n) =>
    n.endsWith(".md"),
  );
  return Promise.all(
    names.map(async (name) => ({
      slug: name === "README.md" ? "index" : name.slice(0, -3),
      html: marked
        .parse(await readFile(`docs/product/${name}`, "utf8"))
        .replace(/href="([a-z-]+)\.md"/g, 'href="/docs/$1/"'),
    })),
  );
}
export const docStyle = `body{margin:0;background:#f4f4ee;color:#263a2f;font:15px/1.7 Arial,sans-serif}main{max-width:850px;margin:auto;padding:40px 24px}a{color:#46673e}h1{font-size:40px;line-height:1.15;font-weight:500;letter-spacing:-1px}h2{margin-top:36px;font-size:23px;font-weight:500}pre{background:#e6eadf;overflow:auto;padding:18px;font-size:12px;border-radius:4px}code{font-size:.9em}table{border-collapse:collapse;width:100%;font-size:13px;display:block;overflow:auto}th,td{text-align:left;padding:10px;border-bottom:1px solid #cbd4c2}blockquote{border-left:3px solid #a4b696;padding-left:20px}nav{font-size:13px;display:flex;justify-content:space-between;margin-bottom:35px}`;
