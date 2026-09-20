// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Check the built Modules section against the snapshot it was generated from.
 *
 * check-output.mjs validates the site as a whole and check-reference-output.mjs
 * validates the generated reference; this one holds the module catalog to the
 * three claims it makes. Every module in the snapshot has a page and a row in
 * the static table, so the catalog cannot quietly shrink to what fits on a
 * screen. Every module page links back to the catalog, so the section is
 * navigable from any entry point an agent cites. And the JSON served at the
 * published URL is the snapshot byte for byte, so a reader who takes the data
 * instead of the pages gets the same answer.
 *
 * The wording pass is the one a reviewer cannot do by eye across fifty pages:
 * compatibility in NSX is declared by a manifest, and no page is allowed to
 * report it as a hardware result (AmbiqAI/neuralspotx#259).
 */

import fs from 'node:fs';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(siteRoot, 'dist');
const dataDir = path.join(siteRoot, 'src/data');

// The same class the CLI and configuration pages are held to: a Starlight
// shell plus one table. The catalog is the page that will trip it first, and
// the warning exists so it gets split before it fails.
const HTML_BUDGET = 250_000;
const GZIP_BUDGET = 40_000;
const WARN_AT = 0.8;

/* Phrases that turn a declaration into a hardware claim. NSX runs no per-board
   validation matrix, so none of these may appear on a generated module page.
   Matched case-insensitively against the rendered text. */
const FORBIDDEN = [
  'validated on',
  'tested on',
  'verified on',
  'hardware validated',
  'hardware-validated',
  'known to work on',
  'proven on',
];

// The element the generator wraps the static table in, and the island filters
// through. Scoping the row scan to it is what makes the row count a count of
// rows rather than of links that happen to point at a module.
const CATALOG_TABLE_ID = 'module-catalog';

const errors = [];
const warnings = [];

const fail = (message) => errors.push(message);

const pageFor = (route) => path.join(dist, route, 'index.html');

function readPage(route) {
  const file = pageFor(route);
  if (!fs.existsSync(file)) {
    fail(`missing page for route ${route}`);
    return null;
  }
  return fs.readFileSync(file, 'utf8');
}

/** Rendered text only: scripts carry the island's props and the search index. */
function visibleText(html) {
  return html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ');
}

/** The body rows of the catalog's static table, in document order. */
function catalogRows(html) {
  const anchor = html.indexOf(`id="${CATALOG_TABLE_ID}"`);
  if (anchor === -1) return [];
  const open = html.indexOf('<tbody', anchor);
  const close = html.indexOf('</tbody>', open);
  if (open === -1 || close === -1) return [];
  return [...html.slice(open, close).matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/g)].map(
    (match) => match[0],
  );
}

function measure(route) {
  const file = pageFor(route);
  if (!fs.existsSync(file)) return null;
  const buffer = fs.readFileSync(file);
  const gzip = gzipSync(buffer).byteLength;
  if (buffer.byteLength > HTML_BUDGET || gzip > GZIP_BUDGET) {
    fail(
      `module page over budget: ${route} (${buffer.byteLength} HTML, ${gzip} gzip; ` +
        `budget ${HTML_BUDGET}/${GZIP_BUDGET})`,
    );
  } else if (buffer.byteLength > HTML_BUDGET * WARN_AT || gzip > GZIP_BUDGET * WARN_AT) {
    warnings.push(
      `${route} is at ${Math.round((buffer.byteLength / HTML_BUDGET) * 100)}% of the HTML budget ` +
        `and ${Math.round((gzip / GZIP_BUDGET) * 100)}% of the gzip budget; split it`,
    );
  }
  return { route, bytes: buffer.byteLength, gzip };
}

function main() {
  if (!fs.existsSync(dist)) throw new Error('check-modules: dist/ is missing, run npm run build');
  const reportPath = path.join(dataDir, 'modules-report.json');
  if (!fs.existsSync(reportPath)) {
    throw new Error('check-modules: modules-report.json is missing, run npm run build:modules');
  }
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
  const snapshot = JSON.parse(fs.readFileSync(path.join(dataDir, 'modules.json'), 'utf8'));
  const boards = JSON.parse(fs.readFileSync(path.join(dataDir, 'boards.json'), 'utf8'));

  if (report.moduleCount !== snapshot.modules.length) {
    fail(
      `the report counts ${report.moduleCount} modules and the snapshot holds ${snapshot.modules.length}`,
    );
  }

  const catalog = readPage(report.routes.catalog);
  const overview = readPage(report.routes.overview);
  const boardsPage = readPage(report.routes.boards);

  // Every module: a page, a catalog row, and a way back to the catalog. The
  // rows are read out of the built HTML rather than the generator's output,
  // because the point is what the reader receives, and only out of the table
  // the island filters: a link in the sidebar or in a paragraph is not a row,
  // and counting those would let the table shrink unnoticed.
  const rows = catalog === null ? [] : catalogRows(catalog);
  if (catalog !== null && rows.length === 0) {
    fail(`the catalog page carries no static table under id="${CATALOG_TABLE_ID}"`);
  }
  if (catalog !== null && rows.length !== snapshot.modules.length) {
    fail(
      `the catalog's static table has ${rows.length} rows for ${snapshot.modules.length} ` +
        'modules; the rows must be in the HTML, one per module, not built by the island',
    );
  }

  const catalogLinks = new Set(
    [...rows.join('').matchAll(/href="[^"]*\/modules\/([a-z0-9][a-z0-9-]*)\/"/g)].map(
      (match) => match[1],
    ),
  );
  for (const module of snapshot.modules) {
    const route = `modules/${module.name}`;
    const html = readPage(route);
    if (html === null) continue;
    if (!catalogLinks.has(module.name)) {
      fail(`${module.name} has a page but no row in the catalog table`);
    }
    if (!/href="[^"]*\/modules\/catalog\/"/.test(html)) {
      fail(`${route} does not link back to the catalog`);
    }
    if (!visibleText(html).includes(`nsx module add ${module.name}`)) {
      fail(`${route} does not show the command that adds the module`);
    }
  }

  // The board matrix is every descriptor NSX ships, in the package's order.
  if (boardsPage !== null) {
    const text = visibleText(boardsPage);
    for (const board of boards.boards) {
      if (!text.includes(board.name)) fail(`the board matrix omits ${board.name}`);
    }
    const positions = boards.boards.map((board) => text.indexOf(board.name));
    for (let index = 1; index < positions.length; index += 1) {
      if (positions[index] < positions[index - 1]) {
        fail(
          `the board matrix lists ${boards.boards[index].name} before ` +
            `${boards.boards[index - 1].name}, against the order the package declares`,
        );
        break;
      }
    }
  }

  // Compatibility is declared, everywhere, without exception.
  for (const route of [
    report.routes.overview,
    report.routes.catalog,
    report.routes.boards,
    ...report.modules.map((module) => module.route),
  ]) {
    const html = route === report.routes.catalog ? catalog : readPage(route);
    if (!html) continue;
    const text = visibleText(html).toLowerCase();
    for (const phrase of FORBIDDEN) {
      if (text.includes(phrase)) {
        fail(`${route} says "${phrase}"; compatibility in NSX is declared by a manifest`);
      }
    }
    if (!text.includes('declare')) {
      fail(`${route} never says compatibility is declared`);
    }
  }

  if (overview !== null && !visibleText(overview).includes(String(snapshot.modules.length))) {
    fail('the overview does not report how many modules the registry pins');
  }

  // The published JSON is the snapshot, not a rendering of it.
  for (const [name, source] of [
    ['modules/catalog.json', path.join(dataDir, 'modules.json')],
    ['modules/boards.json', path.join(dataDir, 'boards.json')],
  ]) {
    const served = path.join(dist, name);
    if (!fs.existsSync(served)) {
      fail(`artifact missing at ${name}`);
      continue;
    }
    if (fs.readFileSync(served, 'utf8') !== fs.readFileSync(source, 'utf8')) {
      fail(`${name} differs from the committed snapshot it is copied from`);
    }
  }

  let largest = { route: '', bytes: 0, gzip: 0 };
  for (const route of [
    report.routes.overview,
    report.routes.catalog,
    report.routes.boards,
    ...report.modules.map((module) => module.route),
  ]) {
    const measured = measure(route);
    if (measured && measured.bytes > largest.bytes) largest = measured;
  }

  if (errors.length) {
    for (const message of errors) console.error(`check-modules: ${message}`);
    throw new Error(`check-modules: ${errors.length} problem(s) in the generated Modules section`);
  }
  for (const message of warnings) console.warn(`check-modules: warning: ${message}`);

  console.log(
    `check-modules: ${snapshot.modules.length} modules on ${report.pages} pages, ` +
      `${boards.boards.length} boards, largest ${largest.route} at ${largest.bytes} HTML / ` +
      `${largest.gzip} gzip bytes (budget ${HTML_BUDGET}/${GZIP_BUDGET}).`,
  );
}

main();
