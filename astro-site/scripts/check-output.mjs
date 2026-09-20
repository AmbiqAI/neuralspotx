// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * Post-build contract check over dist/.
 *
 * heliaRT's equivalent is a Python script carrying product-specific checks
 * (operator export, redirect map, Doxygen page budgets), so only its link and
 * anchor pass is portable. This is that pass rewritten in Node, which keeps the
 * docs workflow on one runtime, plus the two facts a scaffold can assert today:
 * the search index shipped, and the footer's provenance is real.
 *
 * A broken internal link is a build failure rather than a warning because the
 * site publishes under a base path, where a missing leading `/neuralspotx/`
 * still renders and only 404s in production.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const site = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(site, 'dist');
const ORIGIN = 'https://ambiqai.github.io';
const BASE = '/neuralspotx/';

if (!fs.existsSync(dist)) throw new Error('No dist/. Run npm run build first.');

const walk = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });

const files = walk(dist);
const htmlFiles = files.filter((file) => file.endsWith('.html'));
if (htmlFiles.length === 0) throw new Error('No built HTML found in dist/.');

/* Script and style bodies hold unescaped `<`, which would read as markup. */
const TAG = /<([a-zA-Z][-a-zA-Z0-9]*)((?:\s+[^\s"'>/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'`=<>]+))?)*)\s*\/?>/g;
const ATTR = /([^\s"'>/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+)))?/g;
const CHECKED_RELS = new Set([
  'canonical',
  'alternate',
  'stylesheet',
  'icon',
  'shortcut icon',
  'apple-touch-icon',
  'sitemap',
  'manifest',
  'preload',
]);

const parse = (html) => {
  const body = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '');
  const ids = new Set();
  const duplicates = new Set();
  const links = [];
  for (const [, tag, attrString] of body.matchAll(TAG)) {
    const attrs = {};
    for (const [, name, dq, sq, bare] of attrString.matchAll(ATTR)) {
      attrs[name.toLowerCase()] = dq ?? sq ?? bare ?? '';
    }
    if (attrs.id) {
      if (ids.has(attrs.id)) duplicates.add(attrs.id);
      ids.add(attrs.id);
    }
    if (attrs.src) links.push(attrs.src);
    /* Anchors, plus the <link rel> targets a broken build silently points at
       a route that was never emitted: canonical and alternate are what a
       crawler follows, and the rest are what the browser fetches. */
    if (attrs.href && (tag === 'a' || (tag === 'link' && CHECKED_RELS.has(attrs.rel ?? '')))) {
      links.push(attrs.href);
    }
  }
  return { ids, duplicates, links };
};

const pages = new Map(htmlFiles.map((file) => [file, parse(fs.readFileSync(file, 'utf8'))]));
const routeOf = (file) =>
  BASE + path.relative(dist, file).split(path.sep).join('/').replace(/index\.html$/, '');
const routes = new Set(htmlFiles.map(routeOf));
const errors = [];

for (const [file, page] of pages) {
  const route = routeOf(file);
  for (const anchor of page.duplicates) errors.push(`${route}: duplicate id ${anchor}`);
  for (const link of page.links) {
    let url;
    try {
      url = new URL(link, ORIGIN + route);
    } catch {
      errors.push(`${route}: unparseable link ${link}`);
      continue;
    }
    if (url.protocol !== 'https:' || url.host !== 'ambiqai.github.io') continue;
    if (!url.pathname.startsWith(BASE)) {
      /* Sibling HELIA sites share the host, so a path outside the base is only
         wrong when the same path exists under the base: that is an author who
         dropped the base prefix, and it would 404 in production only. */
      if (routes.has(BASE + url.pathname.replace(/^\//, ''))) {
        errors.push(`${route}: internal link missing the ${BASE} prefix, ${link}`);
      }
      continue;
    }
    let target = path.join(dist, decodeURIComponent(url.pathname.slice(BASE.length)));
    if (url.pathname.endsWith('/')) target = path.join(target, 'index.html');
    if (!fs.existsSync(target)) {
      errors.push(`${route}: missing ${link}`);
    } else if (url.hash) {
      const fragment = decodeURIComponent(url.hash.slice(1));
      const targetPage = pages.get(target);
      if (targetPage && !targetPage.ids.has(fragment)) errors.push(`${route}: missing anchor ${link}`);
    }
  }
}

if (!fs.existsSync(path.join(dist, 'pagefind/pagefind.js'))) {
  errors.push('No Pagefind index in dist/pagefind/. Site search would be dead.');
}

const buildInfoPath = path.join(dist, 'build-info.json');
if (!fs.existsSync(buildInfoPath)) {
  errors.push('No build-info.json in dist/. The footer provenance is unverifiable.');
} else {
  const build = JSON.parse(fs.readFileSync(buildInfoPath, 'utf8'));
  if (!/^[0-9a-f]{40}$/.test(build.commit ?? '')) errors.push('build-info.json has no source commit');
  if (!build.version) errors.push('build-info.json has no package version');
  const home = fs.readFileSync(path.join(dist, 'index.html'), 'utf8');
  if (!home.includes(build.shortCommit)) errors.push('The footer does not carry the source commit');
  if (!home.includes(build.version)) errors.push('The footer does not carry the package version');
}

/*
 * Home's Markdown rendition.
 *
 * The rendition is derived from MDX source, so anything a component holds in a
 * prop reaches an agent as nothing at all (AmbiqAI/helia-ui#143). Home answers
 * that by carrying the figures and links in prose beside the cards, which only
 * works while the prose and the snapshots agree. This is the pass that makes a
 * stale figure a build failure rather than a number nobody rechecked.
 */
const homeMarkdown = path.join(dist, 'index.md');
if (!fs.existsSync(homeMarkdown)) {
  errors.push('No index.md in dist/. Home has no Markdown rendition.');
} else {
  const rendition = fs.readFileSync(homeMarkdown, 'utf8');
  const dataDir = path.join(site, 'src', 'data');
  const readData = (name) => JSON.parse(fs.readFileSync(path.join(dataDir, name), 'utf8'));
  const modules = readData('modules.json');
  const boards = readData('boards.json');
  const examples = readData('examples.json');
  const toolchains = new Set(boards.boards.flatMap((board) => board.toolchains));

  /* The whole sentence, not the digits in it: a loose search for each number
     passes on a drifted count as soon as the old value survives anywhere else
     on the page, which it does. Whitespace is normalized on both sides because
     the sentence is wrapped in the MDX and rewrapped in the rendition. */
  const flatten = (text) => text.replace(/\s+/g, ' ');
  const coverage =
    `The packaged registry lists ${modules.module_count} modules. ` +
    `NSX ships ${boards.board_count} board descriptors across ` +
    `${Object.keys(boards.soc_families).length} SoC families, declaring ` +
    `${toolchains.size} toolchains between them, and this repository carries ` +
    `${examples.examples.length} example apps.`;
  if (!flatten(rendition).includes(flatten(coverage))) {
    errors.push(`index.md does not carry the coverage sentence verbatim: ${coverage}`);
  }

  /* Every card grid on Home is duplicated as a link list underneath it. An
     example added under examples/ shows up in the grid on its own and has to
     be added to that list by hand, so this is what catches the omission. */
  const required = [
    ...examples.examples.map((example) => example.href),
    '/neuralspotx/guides/examples/',
    '/neuralspotx/guides/apps/app-layout/',
    '/neuralspotx/guides/modules/custom-modules/',
    '/neuralspotx/guides/contribute/adding-a-module/',
    '/neuralspotx/modules/catalog/',
    '/neuralspotx/modules/boards/',
    '/neuralspotx/modules/catalog.json',
    '/neuralspotx/llms.txt',
    '/neuralspotx/reference/releases/',
    '/neuralspotx/getting-started/',
    '/neuralspotx/guides/',
    '/neuralspotx/reference/',
  ].map((route) => ORIGIN + route);
  for (const link of [
    ...required,
    'https://ambiqai.github.io/helia-rt/',
    'https://ambiqai.github.io/ns-cmsis-nn/',
    'https://ambiqai.github.io/helia-aot/',
    'https://github.com/AmbiqAI/heartkit-vitals-demo',
  ]) {
    if (!rendition.includes(`(${link})`)) errors.push(`index.md has no Markdown link to ${link}`);
  }
}

if (errors.length > 0) throw new Error([...new Set(errors)].sort().join('\n'));

const bytes = files.reduce((total, file) => total + fs.statSync(file).size, 0);
console.log(
  `Checked links, assets and unique anchors in ${pages.size} HTML pages.\n` +
    `dist: ${files.length} files, ${(bytes / 1024 / 1024).toFixed(2)} MiB, Pagefind index present.`,
);
