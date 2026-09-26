// Private HTTP report and transparent workbench proxy, bound only to Tailscale IPv4.
import http from "node:http";
import net from "node:net";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const host = execFileSync("tailscale", ["ip", "-4"], { encoding: "utf8" }).trim();
const octets = host.split(".").map(Number);
if (octets.length !== 4 || octets[0] !== 100 || octets[1] < 64 || octets[1] > 127) {
  throw new Error("Expected a Tailscale IPv4 address; refusing a broader bind");
}
const document = path.join(root, "runtime/demo/index.html");
fs.accessSync(document);
const report = http.createServer((request, response) => {
  const pathname = new URL(request.url, "http://demo.invalid").pathname;
  if (!["GET", "HEAD"].includes(request.method)) {
    response.writeHead(405, { Allow: "GET, HEAD" }).end();
    return;
  }
  if (!["/", "/index.html"].includes(pathname)) {
    response.writeHead(404).end("Not found");
    return;
  }
  fs.stat(document, (error, stat) => {
    if (error) { response.writeHead(503).end("Report is rebuilding"); return; }
    response.writeHead(200, {
      "Content-Type": "text/html; charset=utf-8",
      "Content-Length": stat.size,
      "Cache-Control": "no-cache",
      "X-Content-Type-Options": "nosniff",
    });
    if (request.method === "HEAD") { response.end(); return; }
    const stream = fs.createReadStream(document);
    stream.on("error", () => response.destroy());
    response.on("close", () => stream.destroy());
    stream.pipe(response);
  });
});
// Transparent TCP forwarding preserves Host, Origin and SSE without modifying Next.js.
const connections = new Set();
const workbench = net.createServer((client) => {
  const upstream = net.connect({ host: "127.0.0.1", port: 3215 });
  connections.add(client); connections.add(upstream);
  client.pipe(upstream); upstream.pipe(client);
  client.on("error", () => upstream.destroy());
  upstream.on("error", () => client.destroy());
  client.on("close", () => { connections.delete(client); upstream.destroy(); });
  upstream.on("close", () => { connections.delete(upstream); client.destroy(); });
});
for (const server of [report, workbench]) {
  server.on("error", (error) => {
    console.error(`Demo listener failed (${error.code}); no public fallback bind attempted.`);
    process.exit(1);
  });
}
report.listen(8085, host, () => console.log(`Report: http://${host}:8085`));
workbench.listen(8086, host, () => console.log(`Workbench: http://${host}:8086`));
for (const signal of ["SIGTERM", "SIGINT"]) {
  process.on(signal, () => {
    for (const connection of connections) connection.destroy();
    report.close(); workbench.close();
    setTimeout(() => process.exit(0), 250).unref();
  });
}
