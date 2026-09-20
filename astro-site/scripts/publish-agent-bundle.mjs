#!/usr/bin/env node
// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * Rewrite the agent-facing bundle from the models, after the site build.
 *
 * helia-ui's discoverability pass writes llms.txt, llms-full.txt and a `.md`
 * rendition per route by reading the authored source and stripping every tag.
 * Two thirds of this site is generated MDX whose content is component props, so
 * what that pass publishes for those routes is a heading and a docstring: no
 * option tables, no field tables, no signatures. heliaRT hit the same wall and
 * answered it the same way, by republishing the reference part of the bundle
 * from the reference model after the build (astro-site/scripts/
 * publish-reference-markdown.mjs there).
 *
 * This is that, widened to every generated section:
 *
 *   /reference/cli/<slug>/     re-rendered from public/reference/cli.json plus
 *                              the notes file the MDX merges
 *   /reference/config/<id>/    re-rendered from public/reference/config.json
 *   /reference/api/<module>/   taken from the pyref text bundle, which is the
 *                              reference model rendered by the code that built
 *                              the pages
 *   /modules/<slug>/           the plugin's rendition, with the ModuleCard
 *                              facts prepended from the committed snapshot
 *
 * Everything else is authored Markdown and the plugin's rendition is already
 * faithful, so it is left alone. llms-full.txt is then recomposed from the
 * renditions on disk in the plugin's own order and format, and llms.txt gains
 * the machine-readable artifacts, which are what an agent should fetch instead
 * of scraping the pages.
 *
 * Upstream: tasks/256-docs-migration/helia-ui-gaps-261.md.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { flatten, routeFor } from './lib/render-cli.mjs';
import { typeLabel } from './lib/module-types.mjs';
import {
  componentLinksMarkdown,
  moduleFactsMarkdown,
  readNotes,
  renderCliPageMarkdown,
  renderConfigPageMarkdown,
  splitPyrefBundle,
} from './lib/render-agent-markdown.mjs';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(siteRoot, 'dist');
const read = (file) => fs.readFileSync(file, 'utf8');
const readJson = (file) => JSON.parse(read(file));

const indexPath = path.join(dist, 'content-index.json');
if (!fs.existsSync(indexPath)) {
  throw new Error('No dist/content-index.json. Run npm run build first.');
}
const index = readJson(indexPath);
const base = index.base.endsWith('/') ? index.base : `${index.base}/`;
const origin = index.site.replace(/\/$/, '');

const renditionFor = (route) =>
  path.join(dist, route.slice(base.length).replace(/\/$/, ''), 'index.md');

const replacements = new Map();

/* CLI, from the argparse dump the pages were rendered from. */
const cli = readJson(path.join(siteRoot, 'public/reference/cli.json'));
const notesDir = path.join(siteRoot, 'reference-notes/cli');
for (const node of flatten(cli)) {
  const route = `${base}${routeFor(node, 'reference/cli')}/`;
  replacements.set(
    route,
    renderCliPageMarkdown(node, {
      cli,
      notes: readNotes(notesDir, node.slug),
      routePrefix: 'reference/cli',
      base,
      origin,
    }),
  );
}

/* Configuration, from the schema manifest. */
const config = readJson(path.join(siteRoot, 'public/reference/config.json'));
for (const schema of config.schemas) {
  replacements.set(`${base}reference/config/${schema.id}/`, renderConfigPageMarkdown(schema));
}

/*
 * Python API. pyref writes one Markdown section per module into its own text
 * bundle, so the module pages are already model-derived there and only need
 * cutting at the H1 boundaries and keying by route.
 */
const pyref = splitPyrefBundle(read(path.join(siteRoot, 'public/reference/api/llms-full.txt')));
const symbols = readJson(path.join(siteRoot, 'public/reference/python-symbols.json'));
for (const name of symbols.modules) {
  const section = pyref.get(name);
  if (!section) throw new Error(`The pyref bundle has no section for ${name}.`);
  const segments = name.split('.');
  const route = `${base}reference/api/${segments.join('/')}/`;
  /* The per-module JSON is linked from the page but not from pyref's own
     bundle, and it is the artifact an agent should read instead of the page. */
  const json = `${base}reference/api/${segments.join('/')}.json`;
  replacements.set(route, `${section}\n[Machine-readable model](${origin}${json})\n`);
}

/*
 * Modules. The body of a module page is Markdown already; only the card's
 * facts are props, so this prepends them rather than re-rendering the page.
 */
const snapshot = readJson(path.join(siteRoot, 'src/data/modules.json'));
for (const module of snapshot.modules) {
  const route = `${base}modules/${module.slug}/`;
  const file = renditionFor(route);
  if (!fs.existsSync(file)) continue;
  const rendition = read(file);
  const heading = /^#\s.*$/m.exec(rendition);
  const facts = moduleFactsMarkdown(module, { typeLabel: typeLabel(module.type) });
  const insertAt = heading ? heading.index + heading[0].length : 0;
  replacements.set(
    route,
    `${rendition.slice(0, insertAt)}\n\n${facts}${rendition.slice(insertAt)}`,
  );
}

let rewritten = 0;
for (const [route, markdown] of replacements) {
  const file = renditionFor(route);
  if (!fs.existsSync(file)) throw new Error(`No rendition to replace at ${route}.`);
  fs.writeFileSync(file, markdown, 'utf8');
  rewritten += 1;
}

/*
 * Whatever the source of a rendition, a link that only exists as a component
 * prop is still missing from it. This runs over every route rather than the
 * generated ones, because LinkCard is how the hand-written index pages point
 * at their sections.
 */
let relinked = 0;
for (const entry of index.routes) {
  const source = path.join(siteRoot, entry.sourcePath);
  if (!fs.existsSync(source)) continue;
  const file = renditionFor(entry.route);
  const rendition = read(file);
  const links = componentLinksMarkdown(read(source), { base, origin, rendition });
  if (!links) continue;
  fs.writeFileSync(file, `${rendition.trimEnd()}\n${links}`, 'utf8');
  relinked += 1;
}

/*
 * Recompose llms-full.txt from the renditions on disk, keeping the plugin's
 * order and its `<!-- url -->` section markers so the two files stay one
 * format whichever pass wrote a given section.
 */
const sections = index.routes.map((entry) => {
  const file = renditionFor(entry.route);
  if (!fs.existsSync(file)) throw new Error(`No rendition for ${entry.route}.`);
  return `<!-- ${entry.url} -->\n\n${read(file).trim()}`;
});
const bundle = `${sections.join('\n\n---\n\n')}\n`;
fs.writeFileSync(path.join(dist, 'llms-full.txt'), bundle, 'utf8');

/*
 * The artifacts an agent should read instead of the pages. The plugin has no
 * hook for extra llms.txt entries, so the section is appended.
 */
const ARTIFACTS = [
  ['llms-full.txt', 'llms-full.txt', 'every page above as Markdown, in sidebar order'],
  ['modules/catalog.json', 'modules/catalog.json', 'the module catalog: one record per module'],
  ['modules/boards.json', 'modules/boards.json', 'the board matrix'],
  ['reference/api/reference.json', 'reference/api/reference.json', 'the Python API model'],
  ['reference/api/llms-full.txt', 'reference/api/llms-full.txt', 'the Python API as Markdown'],
  ['reference/reference.txt', 'reference/reference.txt', 'the whole reference as text'],
  ['reference/cli.json', 'reference/cli.json', 'every command, subcommand and option'],
  ['reference/config.json', 'reference/config.json', 'the four configuration schemas'],
  ['reference/python-symbols.json', 'reference/python-symbols.json', 'every public Python name'],
  ['content-index.json', 'content-index.json', 'every route with its title and headings'],
  ['build-info.json', 'build-info.json', 'the package version and the source commit'],
];
const llmsPath = path.join(dist, 'llms.txt');
const artifactLines = ARTIFACTS.map(([label, file, note]) => {
  const target = path.join(dist, file);
  if (!fs.existsSync(target)) throw new Error(`llms.txt would link a missing artifact: ${file}`);
  return `- [${label}](${origin}${base}${file}): ${note}`;
});
fs.writeFileSync(
  llmsPath,
  `${read(llmsPath).trimEnd()}\n\n## Machine-readable\n\n${artifactLines.join('\n')}\n`,
  'utf8',
);

const bytes = Buffer.byteLength(bundle);
console.log(
  `agent bundle: ${rewritten} of ${index.routes.length} renditions rebuilt from the models, ` +
    `${relinked} given back their component links, ` +
    `llms-full.txt ${(bytes / 1024).toFixed(0)} KiB over ${sections.length} sections, ` +
    `${ARTIFACTS.length} artifacts listed in llms.txt.`,
);
