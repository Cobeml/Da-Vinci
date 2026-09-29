import { cp, mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
// Only this generated destination is replaced; never touch workspaces or study assets.
await rm("davinci/product/static", { recursive: true, force: true });
await mkdir("davinci/product/static", { recursive: true });
await cp("ui/out", "davinci/product/static", { recursive: true, force: true });
const lock = JSON.parse(await readFile("package-lock.json", "utf8"));
const notices = [];
const inventory = [];
for (const [location, pkg] of Object.entries(lock.packages)) {
  if (!location.startsWith("node_modules/") || pkg.dev) continue;
  inventory.push({
    package: location.replace("node_modules/", ""),
    version: pkg.version,
    license: pkg.license || "See package notices",
  });
  let names = [];
  try {
    names = await readdir(location);
  } catch {
    continue;
  }
  for (const name of names.filter((n) =>
    /^(license|copying|notice)(\.|$)/i.test(n),
  )) {
    try {
      notices.push(
        `\n===== ${location} ${pkg.version} / ${name} =====\n` +
          (await readFile(`${location}/${name}`, "utf8")),
      );
    } catch {}
  }
}
await writeFile(
  "davinci/product/static/THIRD_PARTY_LICENSES.txt",
  notices.join("\n"),
);
await writeFile(
  "davinci/product/static/browser-dependencies.json",
  JSON.stringify(inventory, null, 2),
);
console.log(
  "Bundled static workspace UI and browser dependency notices into Python package.",
);
const { documents, docStyle } = await import("./render_product_docs.mjs");
for (const doc of await documents()) {
  const directory =
    "davinci/product/static/docs" +
    (doc.slug === "index" ? "" : `/${doc.slug}`);
  await mkdir(directory, { recursive: true });
  await writeFile(
    `${directory}/index.html`,
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Da Vinci documentation</title><style>${docStyle}</style></head><body><main><nav><a href="/">← Workspace</a><a href="/docs/">Documentation</a></nav>${doc.html}</main></body></html>`,
  );
}
