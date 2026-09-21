// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Build the Modules section from a hostile snapshot and read the result back.
 *
 * Manifest prose is written in other repositories and rendered into MDX, where
 * `<` opens a tag, `{` opens an expression the build evaluates, a backtick
 * opens a code span and an unclosed attribute fails the build outright.
 * Reading build-modules.mjs is not evidence that none of that reaches a
 * reader, so this generates the section from a fixture snapshot carrying each
 * of those payloads, builds this site with it, and asserts what the built HTML
 * and the built markdown rendition contain.
 *
 * It is the real site's build, into a scratch outDir. The committed snapshot
 * is never written: only the generator's input moves, through
 * NSX_DOCS_MODULES_SNAPSHOT. What it does overwrite is the generated section
 * under src/content/docs/modules, which is gitignored and regenerated from the
 * committed snapshot before this exits (AmbiqAI/neuralspotx#259).
 */

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const scratch = path.join(siteRoot, '.astro', 'modules-escaping');
const astro = path.join(siteRoot, 'node_modules/astro/bin/astro.mjs');

/* Each payload is one way a manifest string can stop being text: a tag a
   browser would act on, an expression the build would evaluate, an attribute
   whose value never closes, and the characters that end a cell, a code span or
   a row. The British spelling is the one a real manifest carries, and it is
   here because the marker that lets it past the site's spell check must not
   reach the markdown rendition. */
const PAYLOADS = {
  tag: '<img src=x onerror=alert(1)>',
  expression: '{7 * 6}',
  attribute: '<div class=broken title="never closed>',
  cell: 'a|b {braces} `backticks` <angles>',
  breakout: '</script><b>injected</b>',
  quoted: 'serialisation', // spelling: allow
};

const HOSTILE = {
  name: 'nsx-hostile',
  slug: 'nsx-hostile',
  project: 'nsx-fixture',
  revision: 'v0.0.1',
  metadata_path: 'modules/nsx-hostile/nsx-module.yaml',
  repo_url: 'https://example.invalid/AmbiqAI/nsx-fixture',
  source_url: 'https://example.invalid/AmbiqAI/nsx-fixture/tree/v0.0.1',
  manifest_source: 'git',
  manifest_error: null,
  type: 'algorithm',
  category: null,
  provider: null,
  version: `1.0.0 ${PAYLOADS.expression}`,
  summary:
    `Summary ${PAYLOADS.tag} and ${PAYLOADS.expression} and ${PAYLOADS.attribute} ` +
    `and ${PAYLOADS.breakout} for ${PAYLOADS.quoted}`,
  capabilities: [PAYLOADS.cell, PAYLOADS.tag, PAYLOADS.quoted, PAYLOADS.breakout],
  use_cases: [`Use case ${PAYLOADS.tag}`, `Use case ${PAYLOADS.expression}`],
  anti_use_cases: [`Not for ${PAYLOADS.attribute}`],
  agent_keywords: [PAYLOADS.cell, PAYLOADS.expression],
  provides: { [PAYLOADS.cell]: PAYLOADS.tag },
  depends: { required: ['nsx-plain'], optional: [PAYLOADS.tag] },
  compatibility: {
    boards: [`apollo510_evb ${PAYLOADS.tag}`],
    socs: [`apollo510 ${PAYLOADS.expression}`],
    toolchains: [`gcc ${PAYLOADS.cell}`],
  },
  constraints: { [PAYLOADS.expression]: { note: PAYLOADS.tag } },
  example_refs: [PAYLOADS.tag],
  integrations: {},
};

const PLAIN = {
  ...HOSTILE,
  name: 'nsx-plain',
  slug: 'nsx-plain',
  project: 'helia-fixture',
  version: '2.0.0',
  summary: 'An ordinary summary, so the catalog has a row that is not hostile.',
  capabilities: ['plain'],
  use_cases: ['plain'],
  anti_use_cases: [],
  agent_keywords: ['plain'],
  provides: {},
  depends: { required: [], optional: [] },
  compatibility: { boards: ['apollo510_evb'], socs: ['apollo510'], toolchains: ['gcc'] },
  constraints: {},
  example_refs: [],
};

const MODULES = {
  schema_version: 1,
  registry_schema_version: 1,
  module_count: 2,
  unchecked_projects: { 'helia-fixture': 'a private repository, so nothing re-reads it' },
  modules: [HOSTILE, PLAIN],
};

const BOARDS = {
  schema_version: 1,
  board_count: 1,
  boards: [
    {
      order: 0,
      name: 'apollo510_evb',
      soc: 'apollo510',
      soc_family: 'apollo510',
      tier: 'primary',
      sdk_provider: 'nsx-ambiqsuite',
      sdk_provider_module: 'nsx-ambiqsuite',
      cpu: { core: 'cortex-m55', float_abi: 'hard', abi: 'aapcs' },
      toolchains: ['gcc'],
      registered: true,
    },
  ],
  soc_families: {
    apollo510: {
      provider: 'nsx-ambiqsuite',
      project: 'nsx-ambiq-sdk',
      revision: 'v5.2.24',
      modules: ['nsx-plain'],
      sdk_modules: [],
      core_modules: [],
    },
  },
};

function run(args, env = {}) {
  return execFileSync(process.execPath, args, {
    cwd: siteRoot,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, ...env },
  });
}

/** The text a reader sees: what sits inside a tag is not it. */
const visibleText = (html) =>
  html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
    .replace(/\s+/g, ' ');

const TAG = /<([a-zA-Z][^\s/>]*)((?:[^>"']|"[^"]*"|'[^']*')*)\/?>/g;

/**
 * Every element in the document, with its attribute names.
 *
 * Attribute values are blanked before the names are read: the filter island's
 * props carry the manifest's own strings, and a payload sitting inside a
 * quoted value is the data it is supposed to be, not an attribute.
 */
function elements(html) {
  const found = [];
  for (const [, name, rawAttributes] of html.matchAll(TAG)) {
    const attributes = rawAttributes.replace(/"[^"]*"/g, '""').replace(/'[^']*'/g, "''");
    found.push({
      name: name.toLowerCase(),
      attributes: [...attributes.matchAll(/(?:^|\s)([A-Za-z_:][-\w:.]*)/g)].map((match) =>
        match[1].toLowerCase(),
      ),
    });
  }
  return found;
}

function assertPage(label, html) {
  /* What the manifest wrote is text on the page, not markup in it. */
  const handlers = elements(html).filter((element) =>
    element.attributes.some((attribute) => attribute.startsWith('on')),
  );
  assert.deepEqual(
    handlers,
    [],
    `${label}: an event handler attribute from the manifest reached the HTML`,
  );
  assert.ok(
    !elements(html).some((element) => element.name === 'img'),
    `${label}: the manifest's <img> was rendered as an element`,
  );
  assert.ok(
    !elements(html).some((element) => element.name === 'b'),
    `${label}: the manifest broke out of the block its description is written into`,
  );
  assert.ok(
    !/<div class=broken/i.test(html),
    `${label}: the manifest's unquoted attribute reached the HTML`,
  );

  const text = visibleText(html);
  assert.ok(text.includes(PAYLOADS.tag), `${label}: the <img ...> payload is not on the page`);
  assert.ok(
    text.includes(PAYLOADS.expression),
    `${label}: the {7 * 6} payload is not on the page as itself`,
  );
  /* 42 is what the page would carry if the build had evaluated it. */
  assert.ok(!text.includes('42'), `${label}: the build evaluated the manifest's expression`);
}

fs.rmSync(scratch, { recursive: true, force: true });
fs.mkdirSync(path.join(scratch, 'snapshot'), { recursive: true });
fs.writeFileSync(
  path.join(scratch, 'snapshot/modules.json'),
  `${JSON.stringify(MODULES, null, 2)}\n`,
);
fs.writeFileSync(path.join(scratch, 'snapshot/boards.json'), `${JSON.stringify(BOARDS, null, 2)}\n`);

const dist = path.join(scratch, 'dist');
try {
  run([path.join(siteRoot, 'scripts/build-modules.mjs')], {
    NSX_DOCS_MODULES_SNAPSHOT: path.join(scratch, 'snapshot'),
    NSX_DOCS_MODULES_PREBUILT: '',
  });
  /* astro.config.mjs imports src/data/build-info.json, which prepare:docs
     writes; on a fresh checkout this test can run first, so it writes it. */
  run([path.join(siteRoot, 'scripts/build-info.mjs')]);

  run([astro, 'build', '--outDir', dist], { NSX_DOCS_MODULES_PREBUILT: '1' });

  const catalog = fs.readFileSync(path.join(dist, 'modules/catalog/index.html'), 'utf8');
  const page = fs.readFileSync(path.join(dist, 'modules/nsx-hostile/index.html'), 'utf8');
  assertPage('catalog', catalog);
  assertPage('module page', page);

  /* The catalog is still a table with a row per module: the payload's pipe
     ended no cell and its backticks opened no code span. */
  const table = catalog.slice(catalog.indexOf('<table'), catalog.indexOf('</table>'));
  assert.equal(
    (table.match(/<tr\b/g) ?? []).length - 1,
    MODULES.modules.length,
    'the catalog table does not carry one body row per fixture module',
  );
  assert.ok(
    visibleText(page).includes(PAYLOADS.cell),
    'the cell payload is not on the module page as the characters the manifest wrote',
  );

  /* The rendition is the same page for a reader who cannot run the site, so
     the marker that quotes an upstream spelling must not be in it. */
  for (const route of ['modules/catalog', 'modules/nsx-hostile']) {
    const rendition = fs.readFileSync(path.join(dist, route, 'index.md'), 'utf8');
    assert.ok(
      !rendition.includes('spelling: allow'),
      `${route}: the spelling marker reached the markdown rendition`,
    );
    assert.ok(
      rendition.includes(PAYLOADS.quoted),
      `${route}: the quoted term is missing from the markdown rendition`,
    );
    /* The rendition is what an agent reads when it cannot run the site, so an
       escaped character has to still be the character the manifest wrote. */
    const rendered = rendition
      .replace(/\\(.)/g, '$1')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&');
    assert.ok(
      rendered.includes(PAYLOADS.tag),
      `${route}: the markdown rendition lost the text the manifest declares`,
    );
  }

  console.log(
    `test-modules-escaping: ${MODULES.modules.length} fixture modules built and read back; ` +
      'manifest prose reaches the page as text.',
  );
} finally {
  /* The section on disk is fixture pages until this runs. */
  run([path.join(siteRoot, 'scripts/build-modules.mjs')], { NSX_DOCS_MODULES_PREBUILT: '' });
  fs.rmSync(scratch, { recursive: true, force: true });
}
