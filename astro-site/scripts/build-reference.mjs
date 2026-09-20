// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Generate the whole Reference section before Astro builds it.
 *
 * Three areas, one pass:
 *   Python API  griffe dump -> scripts/docs/prune_griffe.py -> helia-ui-pyref
 *   CLI         scripts/docs/dump_cli.py -> scripts/lib/render-cli.mjs
 *   Config      scripts/docs/dump_config.py -> scripts/lib/render-config.mjs
 *
 * Everything it writes is generated and gitignored: the MDX under
 * src/content/docs/reference/{api,cli,config}, the artifacts under
 * public/reference, and the sidebar and report under src/data. The pipeline
 * reads only the installed package and the checked-in notes, so CI reproduces
 * it exactly.
 */

import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { renderCli, cliSidebar, flatten } from './lib/render-cli.mjs';
import { renderConfig, configSidebar } from './lib/render-config.mjs';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = path.resolve(siteRoot, '..');

const BASE = '/neuralspotx/';
const GRIFFE_VERSION = '1.7.3';
const SOURCE_URL = 'https://github.com/AmbiqAI/neuralspotx/blob/{commit}/{path}#L{line}';

// Every name in neuralspotx.__all__ carries the same status, so the site says
// so once per page instead of 80 times per page.
const PROVISIONAL_BANNER =
  'The names on this page are <strong>Provisional</strong>: public and supported, ' +
  'but they may change in a minor release.';

const GROUP_LABELS = {
  errors: 'Errors',
  models: 'Models',
  functions: 'Functions',
  emitters: 'Emitters',
};

const MODULE_BLURBS = {
  neuralspotx: 'the typed errors and the structured emitter',
  'neuralspotx.api': 'request objects and the API callables',
  'neuralspotx.models': 'result and report models',
  'neuralspotx.nsx_lock': 'the resolution lock model',
  'neuralspotx.operations': 'operation status enums',
};

const routes = {
  api: 'reference/api',
  cli: 'reference/cli',
  config: 'reference/config',
};

const dirs = {
  api: path.join(siteRoot, 'src/content/docs/reference/api'),
  cli: path.join(siteRoot, 'src/content/docs/reference/cli'),
  config: path.join(siteRoot, 'src/content/docs/reference/config'),
  public: path.join(siteRoot, 'public'),
  data: path.join(siteRoot, 'src/data'),
  work: path.join(siteRoot, '.astro/reference'),
  notes: path.join(siteRoot, 'reference-notes/cli'),
};

const timings = [];

function timed(label, fn) {
  const started = process.hrtime.bigint();
  const result = fn();
  const ms = Number(process.hrtime.bigint() - started) / 1e6;
  timings.push({ label, ms: Math.round(ms) });
  return result;
}

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: repoRoot,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    ...options,
  });
}

function commitSha() {
  if (process.env.DOCS_SOURCE_COMMIT) return process.env.DOCS_SOURCE_COMMIT.trim();
  try {
    return run('git', ['rev-parse', 'HEAD']).trim();
  } catch {
    return '';
  }
}

/**
 * Finish the pages pyref wrote.
 *
 * Starlight renders frontmatter `banner` once per page, which is where the
 * Provisional status belongs; pyref has no status field of its own
 * (AmbiqAI/helia-ui, gaps note). pyref also titles a page with the module's
 * leaf name, so `neuralspotx.api` arrives as "api"; the dotted path is what a
 * reader needs in a tab title and a search result. The sidebar is built
 * separately and keeps its short labels.
 */
function finalizeApiPages(dir) {
  let touched = 0;
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        visit(full);
        continue;
      }
      if (entry.name !== 'index.mdx') continue;
      const text = fs.readFileSync(full, 'utf8');
      if (!text.startsWith('---\n')) continue;
      const end = text.indexOf('\n---', 4);
      if (end === -1) continue;

      const dotted = path.relative(dir, path.dirname(full)).split(path.sep).join('.');
      let head = text.slice(0, end);
      if (dotted) {
        head = head.replace(/^title:.*$/m, `title: ${JSON.stringify(dotted)}`);
      }
      if (!head.includes('\nbanner:')) {
        head += `\nbanner:\n  content: ${JSON.stringify(PROVISIONAL_BANNER)}`;
      }
      fs.writeFileSync(full, head + text.slice(end), 'utf8');
      touched += 1;
    }
  };
  visit(dir);
  return touched;
}

/**
 * Group the Python sidebar by category rather than by module. pyref has no
 * grouping control (AmbiqAI/helia-ui#74), so the grouping is applied here from
 * the catalog prune_griffe.py emits alongside the model.
 */
function apiSidebar(catalog) {
  const items = [{ label: 'Overview', slug: routes.api }];
  for (const category of Object.keys(GROUP_LABELS)) {
    const members = catalog.symbols
      .filter((symbol) => symbol.category === category)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!members.length) continue;
    items.push({
      label: GROUP_LABELS[category],
      collapsed: true,
      // Starlight applies the site base to sidebar links itself, so these stay
      // base-relative while the in-page markdown links carry it.
      items: members.map((symbol) => ({
        label: symbol.name,
        link: `/${routes.api}/${symbol.module.split('.').join('/')}/#${symbol.path}`,
      })),
    });
  }
  return items;
}

function textBundle({ catalog, cli, config, pyrefBundle }) {
  const lines = [
    '# neuralSPOT-X reference',
    '',
    'Generated from the installed package: the public Python API, the CLI and the',
    'configuration schemas.',
    '',
    '## Python API',
    '',
  ];
  for (const symbol of catalog.symbols) {
    lines.push(`- ${symbol.path} (${symbol.kind}, ${symbol.category})`);
  }
  lines.push('', '## CLI', '');
  for (const node of flatten(cli)) {
    const alias = node.alias_of ? ` (alias for nsx ${node.alias_of})` : '';
    lines.push(`- nsx ${node.name}${alias}: ${node.help ?? ''}`);
    for (const argument of node.arguments) {
      lines.push(`    ${argument.flags.join(', ') || argument.name}: ${argument.help ?? ''}`);
    }
  }
  lines.push('', '## Configuration', '');
  for (const schema of config.schemas) {
    lines.push(`### ${schema.file}`, '');
    for (const field of schema.fields) {
      lines.push(`- ${field.path} (${field.type}): ${field.description}`);
    }
    lines.push('');
  }
  lines.push('## Python API detail', '', pyrefBundle);
  return lines.join('\n');
}

function main() {
  // CI generates the reference once, as its own timed step, then runs check
  // and build; both of those would otherwise regenerate it through their pre*
  // hooks. The workflow sets this for those later steps only. Locally the
  // variable is unset, so `npm run build` still generates as it always has.
  if (process.env.NSX_DOCS_REFERENCE_PREBUILT === '1') {
    const report = path.join(dirs.data, 'reference-report.json');
    if (fs.existsSync(report)) {
      console.log('reference: already generated for this job, skipping regeneration.');
      return;
    }
    console.log('reference: NSX_DOCS_REFERENCE_PREBUILT is set but no report exists, generating.');
  }

  const commit = commitSha();
  fs.mkdirSync(dirs.work, { recursive: true });
  fs.mkdirSync(dirs.data, { recursive: true });
  for (const key of ['api', 'cli', 'config']) {
    fs.rmSync(dirs[key], { recursive: true, force: true });
    fs.mkdirSync(dirs[key], { recursive: true });
  }

  const griffeDump = path.join(dirs.work, 'griffe.json');
  const prunedDump = path.join(dirs.work, 'griffe-public.json');
  const catalogPath = path.join(dirs.work, 'catalog.json');
  const cliPath = path.join(dirs.work, 'cli.json');
  const configPath = path.join(dirs.work, 'config.json');

  timed('griffe dump', () => {
    const dump = run('uv', [
      'run',
      '--with',
      `griffe==${GRIFFE_VERSION}`,
      'griffe',
      'dump',
      'neuralspotx',
      '--docstyle',
      'google',
      '-f',
    ]);
    fs.writeFileSync(griffeDump, dump, 'utf8');
  });

  timed('prune griffe', () =>
    run(
      'uv',
      [
        'run',
        'python',
        'scripts/docs/prune_griffe.py',
        '--input',
        griffeDump,
        '--output',
        prunedDump,
        '--catalog',
        catalogPath,
      ],
      { stdio: ['ignore', 'inherit', 'inherit'] },
    ),
  );

  const catalog = JSON.parse(fs.readFileSync(catalogPath, 'utf8'));

  const pyrefResult = timed('pyref', () =>
    spawnSync(
      path.join(siteRoot, 'node_modules/.bin/helia-ui-pyref'),
      [
        '--input', prunedDump,
        '--out', dirs.api,
        '--public', dirs.public,
        '--base', BASE,
        '--package', 'neuralspotx',
        '--route-prefix', routes.api,
        '--source-root', repoRoot,
        '--source-url', SOURCE_URL.replace('{commit}', commit || 'main'),
        ...(commit ? ['--commit', commit] : []),
      ],
      { cwd: siteRoot, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 },
    ),
  );

  if (pyrefResult.error) throw pyrefResult.error;
  const pyrefOutput = `${pyrefResult.stdout ?? ''}${pyrefResult.stderr ?? ''}`;
  if (pyrefResult.status !== 0) {
    throw new Error(`build-reference: pyref exited ${pyrefResult.status}:\n${pyrefOutput}`);
  }

  // pyref prints each unresolved cross-reference as `pyref warning: ...` on
  // stderr and exits 0, so both streams have to be read and the token has to
  // be the one pyref actually emits.
  const warnings = (pyrefOutput.match(/^pyref warning:/gm) ?? []).length;
  if (warnings > 0) {
    throw new Error(
      `build-reference: pyref reported ${warnings} unresolved cross-references:\n${pyrefOutput}`,
    );
  }

  // pyref writes the package page at reference/api/neuralspotx; the section
  // needs an index at reference/api itself.
  const bannered = finalizeApiPages(dirs.api);
  fs.writeFileSync(
    path.join(dirs.api, 'index.mdx'),
    [
      '---',
      'title: "Python API reference"',
      'description: "Every name exported from neuralspotx, generated from the installed package."',
      `banner:\n  content: ${JSON.stringify(PROVISIONAL_BANNER)}`,
      '---',
      '',
      `The \`neuralspotx\` package exports ${catalog.symbols.length} names. Every one of them can be`,
      'imported from the package root; each is documented on the module it is exported from, and',
      'the sidebar groups them as errors, models, functions and emitters.',
      '',
      ...[...new Set(catalog.symbols.map((symbol) => symbol.module))].sort().map((module) => {
        const count = catalog.symbols.filter((symbol) => symbol.module === module).length;
        const route = `${BASE}${routes.api}/${module.split('.').join('/')}/`;
        return `- [\`${module}\`](${route}) ${MODULE_BLURBS[module] ?? ''} (${count})`;
      }),
      '',
      `The same model is published as [JSON](${BASE}${routes.api}/reference.json) and as a`,
      `[text bundle](${BASE}reference/reference.txt).`,
      '',
    ].join('\n'),
    'utf8',
  );

  const cli = timed('dump cli', () => {
    run('uv', ['run', 'python', 'scripts/docs/dump_cli.py', '--output', cliPath]);
    return JSON.parse(fs.readFileSync(cliPath, 'utf8'));
  });

  const cliResult = timed('render cli', () =>
    renderCli({
      cli,
      outDir: dirs.cli,
      notesDir: dirs.notes,
      routePrefix: routes.cli,
      base: BASE,
    }),
  );

  const config = timed('dump config', () => {
    run('uv', ['run', 'python', 'scripts/docs/dump_config.py', '--output', configPath]);
    return JSON.parse(fs.readFileSync(configPath, 'utf8'));
  });

  const configResult = timed('render config', () =>
    renderConfig({ manifest: config, outDir: dirs.config, routePrefix: routes.config, base: BASE }),
  );

  const publicRef = path.join(dirs.public, 'reference');
  fs.mkdirSync(publicRef, { recursive: true });
  fs.copyFileSync(cliPath, path.join(publicRef, 'cli.json'));
  fs.copyFileSync(configPath, path.join(publicRef, 'config.json'));
  fs.copyFileSync(catalogPath, path.join(publicRef, 'python-symbols.json'));
  const pyrefBundle = fs.readFileSync(path.join(dirs.public, routes.api, 'llms-full.txt'), 'utf8');
  fs.writeFileSync(
    path.join(publicRef, 'reference.txt'),
    textBundle({ catalog, cli, config, pyrefBundle }),
    'utf8',
  );

  const sidebar = {
    api: apiSidebar(catalog),
    cli: cliSidebar(cli, { routePrefix: routes.cli }),
    config: configSidebar(config, { routePrefix: routes.config }),
  };
  fs.writeFileSync(
    path.join(dirs.data, 'reference-sidebar.json'),
    `${JSON.stringify(sidebar, null, 2)}\n`,
    'utf8',
  );

  const cliNodes = flatten(cli);
  const report = {
    commit,
    griffeVersion: GRIFFE_VERSION,
    base: BASE,
    unresolvedReferences: warnings,
    provisionalBanners: bannered + 1,
    python: {
      route: routes.api,
      pages: catalog.modules.length + 1,
      symbols: catalog.symbols.map((symbol) => ({
        name: symbol.name,
        anchor: symbol.path,
        route: `${routes.api}/${symbol.module.split('.').join('/')}`,
        category: symbol.category,
      })),
      supporting: catalog.supporting,
      crossReferenceRewrites: catalog.crossReferenceRewrites,
    },
    cli: {
      route: routes.cli,
      pages: cliResult.pages.length,
      notesMerged: cliResult.notesMerged,
      commands: cliNodes.map((node) => ({
        name: node.name,
        route: `${routes.cli}/${node.slug}`,
        aliasOf: node.alias_of ?? null,
      })),
      distinctCommands: cli.commands.filter((command) => !command.alias_of).length,
    },
    config: {
      route: routes.config,
      pages: configResult.pages.length,
      schemas: config.schemas.map((schema) => ({
        id: schema.id,
        file: schema.file,
        route: `${routes.config}/${schema.id}`,
        fields: schema.fields.length,
      })),
    },
    artifacts: {
      model: `${routes.api}/reference.json`,
      pythonBundle: `${routes.api}/llms-full.txt`,
      symbols: 'reference/python-symbols.json',
      cli: 'reference/cli.json',
      config: 'reference/config.json',
      bundle: 'reference/reference.txt',
    },
    timings,
  };
  fs.writeFileSync(
    path.join(dirs.data, 'reference-report.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  );
  fs.writeFileSync(path.join(publicRef, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');

  const total = timings.reduce((sum, entry) => sum + entry.ms, 0);
  console.log(
    `reference: ${report.python.symbols.length} Python symbols on ${report.python.pages} pages, ` +
      `${cliNodes.length} CLI commands on ${report.cli.pages} pages ` +
      `(${cliResult.notesMerged} with hand-written notes), ` +
      `${report.config.pages} configuration pages, ` +
      `${warnings} unresolved references, ${total} ms total.`,
  );
  console.log(`reference timings: ${timings.map((t) => `${t.label} ${t.ms}ms`).join(', ')}`);

  if (process.env.GITHUB_STEP_SUMMARY) {
    const summary = [
      '### Reference generation',
      '',
      '| Stage | Duration |',
      '| --- | --- |',
      ...timings.map((entry) => `| ${entry.label} | ${entry.ms} ms |`),
      `| **total** | **${total} ms** |`,
      '',
      '| Area | Pages | Items |',
      '| --- | --- | --- |',
      `| Python API | ${report.python.pages} | ${report.python.symbols.length} symbols |`,
      `| CLI | ${report.cli.pages} | ${cliNodes.length} commands, ${report.cli.distinctCommands} distinct |`,
      `| Configuration | ${report.config.pages} | ${config.schemas.length} schemas |`,
      `| Unresolved references | ${warnings} | |`,
      '',
    ].join('\n');
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `${summary}\n`);
  }
}

main();
