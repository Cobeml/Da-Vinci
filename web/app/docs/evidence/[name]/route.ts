import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
function root() {
  const local = join(process.cwd(), "docs/product");
  try { readdirSync(local); return local; } catch { return join(process.cwd(), "../docs/product"); }
}
const names = () => readdirSync(root()).filter(n => /^(?:[a-z-]+-results|memory-benchmark)\.json$/.test(n));
export function generateStaticParams() { return names().map(name => ({ name })); }
export const dynamicParams = false;
export async function GET(_request: Request, { params }: { params: Promise<{name: string}> }) {
  const {name} = await params;
  if (!names().includes(name)) return new Response("Not found", {status: 404});
  return new Response(readFileSync(join(root(), name), "utf8"), {headers: {"Content-Type": "application/json"}});
}
