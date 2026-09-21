#!/usr/bin/env node
// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * Read the agent-facing contract back off dist/.
 *
 * check-output.mjs already proves the HTML hangs together. This proves the part
 * a person never looks at: the bundle an agent reads, the renditions it reads
 * it from, the redirects that keep the MkDocs URLs alive, and the head tags a
 * crawler follows.
 *
 * Every assertion here is about content, not existence. A completeness check
 * that only counts files passes a build where the reference model emptied out,
 * which is precisely the failure this phase exists to catch: helia-ui's own
 * pass builds the bundle from authored source, so a generated page's tables
 * vanish from it without changing a single file count.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import crypto from 'node:crypto';
import { flatten } from './lib/render-cli.mjs';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(siteRoot, 'dist');
if (!fs.existsSync(dist)) throw new Error('No dist/. Run npm run build first.');

const read = (file) => fs.readFileSync(file, 'utf8');
const readJson = (file) => JSON.parse(read(file));
const errors = [];
const fail = (message) => errors.push(message);

const index = readJson(path.join(dist, 'content-index.json'));
const base = index.base.endsWith('/') ? index.base : `${index.base}/`;
const origin = index.site.replace(/\/$/, '');
/* The plugin indexes /404/ as a content route and writes it a rendition, while
   emitting the page itself as dist/404.html and excluding it from its own
   checker. It is not content, so it is checked as a 404 below and nowhere as a
   route. */
const routes = index.routes.filter((entry) => entry.route !== `${base}404/`);
const dirFor = (route) => path.join(dist, route.slice(base.length).replace(/\/$/, ''));

// ---------------------------------------------------------------- bundle

const bundle = read(path.join(dist, 'llms-full.txt'));
const llms = read(path.join(dist, 'llms.txt'));

/*
 * Cut the bundle at its section markers and assert against the section a fact
 * belongs to, never against the file.
 *
 * A corpus-wide substring search is not a completeness check: `nsx-audio` is
 * named on a dozen other pages, so deleting its page and its index entry leaves
 * every `bundle.includes('nsx-audio')` true and the build green. Keyed by route,
 * the same deletion is a failure with the route in the message.
 */
const sectionsOf = (text) => {
  /* Only the absolute-URL markers open a section; the composer's own nsx: block
     markers are page content. */
  const marks = [...text.matchAll(/^<!-- (https:\/\/\S+) -->$/gm)];
  return new Map(
    marks.map((mark, position) => [
      mark[1],
      text.slice(mark.index + mark[0].length, marks[position + 1]?.index ?? text.length),
    ]),
  );
};
const sections = sectionsOf(bundle);

/** The section for a route, or a recorded failure and null. */
const sectionFor = (route, what) => {
  const url = `${origin}${route}`;
  const section = sections.get(url);
  if (section === undefined) fail(`llms-full.txt has no section for ${route}, which ${what}`);
  return section ?? null;
};

const present = (section, needle) => section !== null && section.includes(needle);

const symbols = readJson(path.join(siteRoot, 'public/reference/python-symbols.json'));
/* python-symbols.json is generated from neuralspotx.__all__ and pinned to it by
   tests/test_public_surface_doc.py, so asserting against it asserts against
   __all__ without importing the package from a Node check. */
let symbolsFound = 0;
for (const symbol of symbols.symbols) {
  const route = `${base}reference/api/${symbol.module.split('.').join('/')}/`;
  const section = sectionFor(route, `documents ${symbol.path}`);
  if (present(section, symbol.path)) symbolsFound += 1;
  else if (section !== null) fail(`${route}: the bundle section does not name ${symbol.path}`);
}

const cli = readJson(path.join(siteRoot, 'public/reference/cli.json'));
let commandsFound = 0;
for (const node of flatten(cli)) {
  const route = `${base}reference/cli/${node.slug}/`;
  const section = sectionFor(route, `documents nsx ${node.name}`);
  if (section === null) continue;
  if (!section.includes(`# nsx ${node.name}`)) {
    fail(`${route}: the bundle section does not open on nsx ${node.name}`);
    continue;
  }
  commandsFound += 1;
  /* An option table that survived as a table, not as prose about one. */
  for (const argument of node.arguments.filter((entry) => !entry.positional)) {
    const flag = argument.flags[0];
    if (!section.includes(`| ${flag}`)) fail(`${route}: no option row for ${flag}`);
  }
}

const config = readJson(path.join(siteRoot, 'public/reference/config.json'));
for (const schema of config.schemas) {
  const route = `${base}reference/config/${schema.id}/`;
  const section = sectionFor(route, `documents ${schema.file}`);
  if (section === null) continue;
  for (const field of schema.fields) {
    if (!section.includes(`| ${field.path} |`)) fail(`${route}: no field row for ${field.path}`);
  }
}

const snapshot = readJson(path.join(siteRoot, 'src/data/modules.json'));
let modulesFound = 0;
for (const module of snapshot.modules) {
  const route = `${base}modules/${module.slug}/`;
  const section = sectionFor(route, `is a module the registry pins`);
  if (present(section, module.name)) modulesFound += 1;
  else if (section !== null) fail(`${route}: the bundle section does not name ${module.name}`);
}

for (const entry of routes) {
  if (!sections.has(entry.url)) fail(`llms-full.txt has no section for ${entry.url}`);
}
for (const url of sections.keys()) {
  if (!routes.some((entry) => entry.url === url)) fail(`llms-full.txt carries ${url}, which is not a route`);
}

/* The page that says a page is missing is not content. */
for (const [name, text] of [['llms.txt', llms], ['llms-full.txt', bundle]]) {
  if (text.includes(`${base}404/`)) fail(`${name} lists the 404 page`);
}

const REQUIRED_ARTIFACTS = [
  'modules/catalog.json',
  'modules/boards.json',
  'reference/api/reference.json',
  'reference/reference.txt',
  'reference/cli.json',
  'reference/config.json',
  'build-info.json',
];
for (const artifact of REQUIRED_ARTIFACTS) {
  if (!fs.existsSync(path.join(dist, artifact))) fail(`dist is missing ${artifact}`);
  if (!llms.includes(`${base}${artifact}`)) fail(`llms.txt does not list ${artifact}`);
}

/*
 * helia-ui files any page it cannot give a sidebar trail under "Other pages".
 * That is silent: the page is still listed, still counted, and still has a
 * rendition, so nothing in a build log says an agent reading llms.txt by
 * section will never arrive at it. Only two routes are allowed there, and
 * both are deliberately outside the sidebar; anything a generator emits has
 * to be placed by the generator that emits it.
 */
const OTHER_PAGES_ALLOWED = new Set([`${base}`, `${base}404/`]);
const otherPages = llms.split(/^## /m).find((section) => section.startsWith('Other pages'));
if (otherPages) {
  for (const [, url] of otherPages.matchAll(/\]\((\S+?)index\.md\)/g)) {
    const route = url.slice(origin.length);
    if (!OTHER_PAGES_ALLOWED.has(route)) {
      fail(`llms.txt files ${route} under "Other pages"; give it a sidebar entry`);
    }
  }
}

// ------------------------------------------------------------ renditions

/*
 * The rendition is Markdown. Anything here is MDX that leaked through.
 *
 * Scanned outside fenced code, because a docstring may legitimately show a
 * placeholder such as `<ISO 8601 UTC>` in an example block; a component is a
 * capitalized tag that either carries an attribute or closes itself.
 */
const LEAKS = [/^export const\b/m, /\{\s*\/\*/, /<[A-Z][A-Za-z0-9]*(?:\s+[a-zA-Z-]+=|\s*\/>)/];
const LEAK_NAMES = ['an export statement', 'a JSX comment', 'component markup'];
const outsideCode = (markdown) => markdown.replace(/^(```|~~~)[\s\S]*?^\1.*$/gm, '');

const articleOf = (html) => {
  const open = /<div[^>]*class="[^"]*\bsl-markdown-content\b[^"]*"[^>]*>/.exec(html);
  if (!open) return null;
  let depth = 1;
  const tags = /<(\/?)div\b[^>]*>/g;
  tags.lastIndex = open.index + open[0].length;
  let match;
  while ((match = tags.exec(html))) {
    depth += match[1] ? -1 : 1;
    if (depth === 0) return html.slice(open.index + open[0].length, match.index);
  }
  return html.slice(open.index + open[0].length);
};

const stripTags = (html) => html.replace(/<[^>]*>/g, '').replace(/\s+/g, ' ').trim();
const unescape = (text) =>
  text
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&');

let renditions = 0;
for (const entry of routes) {
  const dir = dirFor(entry.route);
  const markdown = path.join(dir, 'index.md');
  if (!fs.existsSync(markdown)) {
    fail(`${entry.route}: no .md rendition`);
    continue;
  }
  renditions += 1;
  const rendition = read(markdown);
  const html = read(path.join(dir, 'index.html'));

  const prose = outsideCode(rendition);
  LEAKS.forEach((pattern, position) => {
    if (pattern.test(prose)) fail(`${entry.route}: the rendition carries ${LEAK_NAMES[position]}`);
  });

  const h1 = /<h1[^>]*>([\s\S]*?)<\/h1>/.exec(html);
  if (!h1) {
    fail(`${entry.route}: the page has no <h1>`);
  } else {
    const heading = unescape(stripTags(h1[1]));
    const rendered = /^#\s+(.+)$/m.exec(rendition)?.[1]?.trim();
    if (rendered !== heading) {
      fail(`${entry.route}: the rendition opens on "${rendered}", the page on "${heading}"`);
    }
  }

  const article = articleOf(html);
  if (article === null) {
    fail(`${entry.route}: no article body in the HTML`);
    continue;
  }
  const links = new Set(
    [...article.matchAll(/href="([^"]+)"/g)]
      .map((match) => match[1].split('#')[0])
      /* _astro/ holds the stylesheets a component injects into the body, which
         are assets rather than links a reader or an agent would follow. */
      .filter((href) => href.startsWith(base) && !href.startsWith(`${base}_astro/`)),
  );
  /* Every link the page offers a reader has to reach an agent too, whether the
     discoverability pass read it off a card's props or out of the prose. */
  for (const href of links) {
    if (!rendition.includes(href)) fail(`${entry.route}: the rendition drops the link to ${href}`);
  }
}

// ------------------------------------------------------------- redirects

const oldRoutes = readJson(path.join(siteRoot, 'src/data/redirects.json'));
let stubs = 0;
let unchanged = 0;
for (const [from, to] of Object.entries(oldRoutes)) {
  if (!to.startsWith(base)) {
    fail(`redirect ${from} leaves the site, ${to}`);
    continue;
  }
  const target = path.join(dist, to.slice(base.length), 'index.html');
  if (!fs.existsSync(target)) {
    fail(`redirect ${from} points at ${to}, which is not in dist`);
    continue;
  }
  if (to === `${base}${from.replace(/^\//, '')}`) {
    unchanged += 1;
    continue;
  }
  const stub = path.join(dist, from.replace(/^\//, ''), 'index.html');
  if (!fs.existsSync(stub)) {
    fail(`old route ${from} emits no redirect stub`);
    continue;
  }
  const html = read(stub);
  if (!/<meta[^>]*http-equiv="refresh"/i.test(html)) fail(`${from}: the stub has no refresh`);
  if (!html.includes(to)) fail(`${from}: the stub does not point at ${to}`);
  if (!/name="robots"[^>]*content="noindex"/i.test(html)) fail(`${from}: the stub is indexable`);
  stubs += 1;
}

// ------------------------------------------------------------------- 404

const notFound = path.join(dist, '404.html');
if (!fs.existsSync(notFound)) {
  fail('No 404.html. A missing page would fall through to the host default.');
} else {
  const html = read(notFound);
  /* A timed redirect takes the reader off the page before they read why they
     are on it, and it turns a hard 404 into a soft one for a crawler. */
  if (/<meta[^>]*http-equiv="refresh"/i.test(html)) fail('404.html redirects on a timer');
  if (!/<link[^>]*rel="canonical"[^>]*>/i.test(html)) fail('404.html has no canonical link');
  for (const href of [`${base}`, `${base}reference/`]) {
    if (!html.includes(`href="${href}"`)) fail(`404.html does not link ${href}`);
  }
}

// --------------------------------------------------------------- sitemap

const sitemapIndex = path.join(dist, 'sitemap-index.xml');
if (!fs.existsSync(sitemapIndex)) {
  fail('No sitemap-index.xml.');
} else {
  const shards = [...read(sitemapIndex).matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  if (shards.length === 0) fail('sitemap-index.xml lists no sitemap.');
  const locations = new Set();
  for (const shard of shards) {
    if (!shard.startsWith(`${origin}${base}`)) fail(`sitemap-index.xml points outside the base, ${shard}`);
    const file = path.join(dist, shard.slice(`${origin}${base}`.length));
    if (!fs.existsSync(file)) {
      fail(`sitemap-index.xml points at ${shard}, which is not in dist`);
      continue;
    }
    for (const [, url] of read(file).matchAll(/<loc>([^<]+)<\/loc>/g)) locations.add(url);
  }
  for (const url of locations) {
    if (!url.startsWith(`${origin}${base}`)) fail(`sitemap: ${url} is outside the canonical origin`);
  }
  if (locations.has(`${origin}${base}404/`)) fail('sitemap: the 404 page is listed');
  for (const from of Object.keys(oldRoutes)) {
    const url = `${origin}${base}${from.replace(/^\//, '')}`;
    if (oldRoutes[from] !== `${base}${from.replace(/^\//, '')}` && locations.has(url)) {
      fail(`sitemap: the redirect stub ${from} is listed`);
    }
  }
  const expected = new Set(routes.map((entry) => entry.url));
  for (const url of expected) if (!locations.has(url)) fail(`sitemap: ${url} is missing`);

  const robots = path.join(dist, 'robots.txt');
  if (!fs.existsSync(robots)) fail('No robots.txt.');
  else if (!read(robots).includes(`${origin}${base}sitemap-index.xml`)) {
    fail('robots.txt does not point at the sitemap index.');
  }
}

// --------------------------------------------------------------- JSON-LD

/*
 * helia-ui serializes the JSON-LD graph with JSON.stringify and drops it into a
 * <script> block unescaped, so a `</script` inside a description would close the
 * block early and the rest of the object would land in the document. Nothing on
 * this site writes one today and the module generator strips the characters, so
 * this fails closed on the input rather than waiting for the output to break.
 * Upstream: tasks/256-docs-migration/helia-ui-gaps-261.md.
 */
for (const entry of index.routes) {
  const description = entry.description ?? '';
  const offenders = ['<', '>', '</script'].filter((token) => description.includes(token));
  if (offenders.length > 0) {
    fail(`${entry.route}: the description carries ${offenders.join(' and ')}, which the JSON-LD block does not escape`);
  }
  if (!description.trim()) fail(`${entry.route}: no description, so the JSON-LD headline is the site default`);
}
for (const entry of routes) {
  const html = read(path.join(dirFor(entry.route), 'index.html'));
  const block = /<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(html);
  if (!block) {
    fail(`${entry.route}: no JSON-LD block`);
    continue;
  }
  try {
    JSON.parse(block[1]);
  } catch (error) {
    fail(`${entry.route}: the JSON-LD block does not parse, ${error.message}`);
  }
}

/*
 * Idempotence. The composer replaces rather than appends, so running it a second
 * time over one dist must change nothing. An appending pass would double every
 * module's facts block and the machine-readable section, and every assertion
 * above would still pass on the doubled file, which is why this is checked
 * rather than reasoned about.
 */
const digest = () => {
  const hash = crypto.createHash('sha256');
  for (const file of ['llms.txt', 'llms-full.txt'].map((name) => path.join(dist, name))) {
    hash.update(read(file));
  }
  for (const entry of routes) hash.update(read(path.join(dirFor(entry.route), 'index.md')));
  return hash.digest('hex');
};
const before = digest();
try {
  execFileSync(process.execPath, [path.join(siteRoot, 'scripts/publish-agent-bundle.mjs')], {
    cwd: siteRoot,
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  if (digest() !== before) fail('publish-agent-bundle.mjs is not idempotent: a second run changed dist.');
} catch (error) {
  fail(`publish-agent-bundle.mjs does not survive a second run: ${String(error.stderr ?? error.message).trim()}`);
}

if (errors.length > 0) throw new Error([...new Set(errors)].sort().join('\n'));

const bundleBytes = Buffer.byteLength(bundle);
console.log(
  `Agent bundle: ${(bundleBytes / 1024).toFixed(0)} KiB over ${sections.size} sections, ` +
    `${symbolsFound} public symbols, ${commandsFound} CLI commands, ${modulesFound} modules.\n` +
    `Renditions: ${renditions} routes, each carrying its H1, every internal link and every link card.\n` +
    `Redirects: ${stubs} stubs plus ${unchanged} old routes that kept their path, ` +
    `${stubs + unchanged} of ${Object.keys(oldRoutes).length} resolved.\n` +
    'Sitemap, robots.txt, the 404 and every JSON-LD block check out.',
);
