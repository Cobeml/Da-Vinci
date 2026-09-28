// Compress display meshes only. Canonical CAD and raw GLBs remain in Atlas/runtime.
import { readdir, readFile, writeFile, mkdir, rename, copyFile } from "node:fs/promises";
import path from "node:path";
import assert from "node:assert/strict";
import { NodeIO, getBounds } from "@gltf-transform/core";
import { ALL_EXTENSIONS } from "@gltf-transform/extensions";
import { meshopt } from "@gltf-transform/functions";
import { MeshoptEncoder, MeshoptDecoder } from "meshoptimizer";

const study = "survey-vtol-cst-v1";
const root = path.resolve("web/public/models/vtol", study);
const archive = path.resolve("runtime", study, "web-originals");
await mkdir(archive, { recursive: true });
await Promise.all([MeshoptEncoder.ready, MeshoptDecoder.ready]);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  "meshopt.encoder": MeshoptEncoder, "meshopt.decoder": MeshoptDecoder,
});
const report = [];
const files = (await readdir(root)).filter(f => f.endsWith(".glb")).sort();
const limit = process.argv.includes("--sample") ? 2 : files.length;
function inventory(doc) {
  const nodes = doc.getRoot().listNodes();
  return {
    names: nodes.map(n => n.getName()).filter(Boolean).sort(),
    triangles: nodes.reduce((total,n) => total + (n.getMesh()?.listPrimitives() ?? []).reduce(
      (count,p) => count + (p.getIndices()?.getCount() ?? p.getAttribute("POSITION").getCount()) / 3, 0), 0),
    bounds: getBounds(doc.getRoot().listScenes()[0]),
  };
}
for (const name of files.slice(0,limit)) {
  const target = path.join(root,name);
  const raw = await readFile(target);
  const doc = await io.readBinary(raw);
  if (doc.getRoot().getExtras().davinciPreviewCompression === 1) continue;
  const before = inventory(doc);
  await doc.transform(meshopt({encoder:MeshoptEncoder,level:"medium",quantizePosition:16,quantizeNormal:12}));
  doc.getRoot().setExtras({...doc.getRoot().getExtras(),davinciPreviewCompression:1});
  const packed = await io.writeBinary(doc);
  const after = inventory(await io.readBinary(packed));
  assert.equal(after.triangles,before.triangles,"Display compression changed triangle count");
  for (const name of before.names) assert(after.names.includes(name),"Display compression lost a part name");
  const error = Math.max(...["min","max"].flatMap(k=>before.bounds[k].map((v,i)=>Math.abs(v-after.bounds[k][i]))));
  assert(error<0.5,"Display bounds changed more than 0.5 mm");
  assert(packed.length<raw.length,"Display compression did not reduce file size");
  await copyFile(target,path.join(archive,name));
  const pending=target+".tmp";
  await writeFile(pending,packed);
  await rename(pending,target);
  const row={name,raw_bytes:raw.length,display_bytes:packed.length,bounds_error_mm:error,triangles:after.triangles};
  report.push(row);
  console.log(JSON.stringify(row));
}
await writeFile(path.join(archive,`compression-${Date.now()}.json`),JSON.stringify(report,null,2));
