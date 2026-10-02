/** Build-time public/installed docs contract: shared navigation, internal links and anchors. */
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {documents, renderDocument} from './render_product_docs.mjs';
const docs = await documents();
const bySlug = new Map(docs.map(doc=>[doc.slug,doc]));
const sections = JSON.parse(await readFile('docs/product/navigation.json','utf8'));
for(const section of sections) for(const item of section.items) assert(bySlug.has(item.slug),`Missing ${item.slug}`);
for(const doc of docs) {
 for(const [,slug,anchor] of doc.html.matchAll(/href="\/docs\/(?:([a-z-]+)\/)?(?:#([^"]+))?"/g)) {
  const target = bySlug.get(slug || 'index');
  assert(target,`${doc.slug}: missing document ${slug}`);
  if(anchor) assert(target.html.includes(`id="${anchor}"`),`${doc.slug}: missing anchor ${slug}#${anchor}`);
 }
}
assert(renderDocument('[index](README.md) [section](memory.md#limits) [evidence](mechanism-results.json)').includes('/docs/evidence/mechanism-results.json'));
assert(bySlug.get('architecture').html.includes('aria-label="Shared experiment lifecycle"'));
console.log(`${docs.length} documents: navigation, links, anchors and lifecycle rendering checked`);
