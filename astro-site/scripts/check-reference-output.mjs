// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Check the built Reference section against the report the generator wrote.
 *
 * check-output.mjs validates the site as a whole; this one validates the
 * generated reference specifically, against src/data/reference-report.json so
 * that a page silently dropped between generation and build is an error
 * rather than a smaller sitemap. The budgets match the ones the helia-rt site
 * uses for its API pages.
 */

import fs from 'node:fs';
import path from 'node:path';
import { gzipSync } from 'node:zlib';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(siteRoot, 'dist');
const reportPath = path.join(siteRoot, 'src/data/reference-report.json');

// Gzip is held at the 40 KB the helia-rt API pages use. The uncompressed
// budget is split by area because the two differ in kind: a Starlight page
// shell measures about 100 KB before any content, a CLI or configuration page
// adds a table on top of that, and a Python API page adds 30-odd rendered
// signatures with their parameter tables at roughly 10 KB each. Holding the
// API pages to the 250 KB the C++ reference uses would cap a page near ten
// symbols and break the grouping the reference is organized around.
//
// Neither budget is comfortably slack, so WARN_AT exists to say so before a
// page trips one: `neuralspotx.api` is the page that will need splitting, and
// it is meant to be split when it crosses 80% of either budget rather than
// when it fails (AmbiqAI/neuralspotx#258).
const GZIP_BUDGET = 40_000;
const WARN_AT = 0.8;
const HTML_BUDGETS = {
  'reference/api': 640_000,
  'reference/cli': 250_000,
  'reference/config': 250_000,
};

function htmlBudget(route) {
  for (const [prefix, budget] of Object.entries(HTML_BUDGETS)) {
    if (route === prefix || route.startsWith(`${prefix}/`)) return budget;
  }
  return 250_000;
}

const warnings = [];

const errors = [];

function fail(message) {
  errors.push(message);
}

function pageFor(route) {
  return path.join(dist, route, 'index.html');
}

function readPage(route) {
  const file = pageFor(route);
  if (!fs.existsSync(file)) {
    fail(`missing page for route ${route}`);
    return null;
  }
  return fs.readFileSync(file, 'utf8');
}

function main() {
  if (!fs.existsSync(dist)) throw new Error('check-reference: dist/ is missing, run npm run build');
  if (!fs.existsSync(reportPath)) {
    throw new Error('check-reference: reference-report.json is missing, run npm run build:reference');
  }
  const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));

  if (report.unresolvedReferences !== 0) {
    fail(`generator reported ${report.unresolvedReferences} unresolved cross-references`);
  }

  // Every public name keeps a stable anchor, and only one of it, so a
  // deep link from the sidebar or from another page cannot go ambiguous.
  const pageCache = new Map();
  const load = (route) => {
    if (!pageCache.has(route)) pageCache.set(route, readPage(route));
    return pageCache.get(route);
  };

  for (const symbol of report.python.symbols) {
    const html = load(symbol.route);
    if (html === null) continue;
    const occurrences = html.split(`id="${symbol.anchor}"`).length - 1;
    if (occurrences === 0) fail(`anchor ${symbol.anchor} is missing from ${symbol.route}`);
    if (occurrences > 1) {
      fail(`anchor ${symbol.anchor} appears ${occurrences} times in ${symbol.route}`);
    }
  }

  // The reference is the public surface and nothing else.
  for (const route of fs.existsSync(path.join(dist, 'reference')) ? walkRoutes('reference') : []) {
    if (route.split('/').some((segment) => segment.startsWith('_'))) {
      fail(`private path published at ${route}`);
    }
  }

  for (const command of report.cli.commands) {
    if (readPage(command.route) === null) continue;
  }
  for (const schema of report.config.schemas) {
    readPage(schema.route);
  }
  readPage(report.python.route);
  readPage(report.cli.route);
  readPage(report.config.route);

  // Per-page budgets, measured on the built HTML the way a reader receives it.
  let largest = { route: '', bytes: 0, gzip: 0 };
  const routes = [
    ...new Set([
      ...report.python.symbols.map((symbol) => symbol.route),
      ...report.cli.commands.map((command) => command.route),
      ...report.config.schemas.map((schema) => schema.route),
      report.python.route,
      report.cli.route,
      report.config.route,
    ]),
  ];
  for (const route of routes) {
    const file = pageFor(route);
    if (!fs.existsSync(file)) continue;
    const buffer = fs.readFileSync(file);
    const gzip = gzipSync(buffer).byteLength;
    if (buffer.byteLength > largest.bytes) {
      largest = { route, bytes: buffer.byteLength, gzip };
    }
    const budget = htmlBudget(route);
    if (buffer.byteLength > budget || gzip > GZIP_BUDGET) {
      fail(
        `reference page over budget: ${route} (${buffer.byteLength} HTML, ${gzip} gzip; ` +
          `budget ${budget}/${GZIP_BUDGET})`,
      );
    } else if (buffer.byteLength > budget * WARN_AT || gzip > GZIP_BUDGET * WARN_AT) {
      warnings.push(
        `${route} is at ${Math.round((buffer.byteLength / budget) * 100)}% of the HTML budget ` +
          `and ${Math.round((gzip / GZIP_BUDGET) * 100)}% of the gzip budget; split it`,
      );
    }
  }

  // The text bundle is what an agent reads instead of the site, so it has to
  // carry every name the pages do. The expected names come out of the built
  // HTML rather than out of the report, because the report is what wrote the
  // bundle: checking one against the other would only prove it agrees with
  // itself.
  const publishedAnchors = new Set();
  for (const route of walkRoutes('reference/api')) {
    const file = pageFor(route);
    if (!fs.existsSync(file)) continue;
    const html = fs.readFileSync(file, 'utf8');
    for (const match of html.matchAll(/id="(neuralspotx(?:\.[A-Za-z_][\w]*)+)"/g)) {
      publishedAnchors.add(match[1]);
    }
  }
  const publishedCommands = new Set(
    walkRoutes('reference/cli')
      .filter((route) => fs.existsSync(pageFor(route)))
      .map((route) => route.slice('reference/cli/'.length))
      .filter(Boolean),
  );

  if (!publishedAnchors.size) fail('no Python anchors found in the built HTML');
  if (!publishedCommands.size) fail('no CLI pages found in the built HTML');

  const bundlePath = path.join(dist, report.artifacts.bundle);
  if (!fs.existsSync(bundlePath)) {
    fail(`text bundle missing at ${report.artifacts.bundle}`);
  } else {
    const bundle = fs.readFileSync(bundlePath, 'utf8');
    for (const anchor of [...publishedAnchors].sort()) {
      if (!bundle.includes(anchor)) fail(`text bundle omits ${anchor}, which the site publishes`);
    }
    for (const slug of [...publishedCommands].sort()) {
      const name = slug.split('-').join(' ');
      if (!bundle.includes(`nsx ${name}`) && !bundle.includes(`nsx ${slug}`)) {
        fail(`text bundle omits the command published at reference/cli/${slug}`);
      }
    }
    for (const schema of report.config.schemas) {
      if (!bundle.includes(schema.file)) fail(`text bundle omits ${schema.file}`);
    }
  }

  for (const artifact of Object.values(report.artifacts)) {
    if (!fs.existsSync(path.join(dist, artifact))) fail(`artifact missing at ${artifact}`);
  }

  if (errors.length) {
    for (const message of errors) console.error(`check-reference: ${message}`);
    throw new Error(`check-reference: ${errors.length} problem(s) in the generated reference`);
  }

  for (const message of warnings) console.warn(`check-reference: warning: ${message}`);

  console.log(
    `check-reference: ${report.python.symbols.length} anchors, ` +
      `${report.cli.commands.length} CLI pages, ${report.config.schemas.length} schema pages, ` +
      `largest ${largest.route} at ${largest.bytes} HTML / ${largest.gzip} gzip bytes ` +
      `(budget ${htmlBudget(largest.route)}/${GZIP_BUDGET}).`,
  );
}

function walkRoutes(relative) {
  const out = [];
  const visit = (current, route) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      const next = route ? `${route}/${entry.name}` : entry.name;
      out.push(next);
      visit(path.join(current, entry.name), next);
    }
  };
  visit(path.join(dist, relative), relative);
  return out;
}

main();
