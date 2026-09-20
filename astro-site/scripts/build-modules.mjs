// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Generate the whole Modules section before Astro builds it.
 *
 * The input is the committed snapshot in src/data: modules.json and
 * boards.json, written by scripts/docs/build_module_data.py from the registry
 * and the module manifests. Nothing here reaches the network, and nothing it
 * writes is committed: the MDX under src/content/docs/modules, the sidebar and
 * report under src/data, and the published catalog under public/modules are
 * all gitignored and regenerated on every dev, check and build run.
 *
 * The catalog's rows are an ordinary Markdown table rather than a component,
 * so Pagefind, the Markdown rendition and a reader with no JavaScript all see
 * every module. The filter island hides rows in that table; it does not own
 * them (AmbiqAI/neuralspotx#259).
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const BASE = '/neuralspotx/';
const ROUTE = 'modules';

// The wildcard a manifest uses to declare every target of a kind. It is a
// facet-free value: a row carrying it matches whatever the reader selects.
const WILDCARD = '*';

// Above this many values a facet is a list rather than a row of chips, so the
// generator collapses it. Capabilities are the only facet that reaches it.
const COLLAPSE_FACET_AT = 16;

const TYPE_ORDER = [
  'sdk_provider',
  'soc',
  'board',
  'runtime',
  'portable_api',
  'algorithm',
  'tooling',
  'backend_specific',
];

const TYPE_GROUPS = {
  sdk_provider: 'SDK providers',
  soc: 'SoC support',
  board: 'Board support',
  runtime: 'Runtimes',
  portable_api: 'Portable APIs',
  algorithm: 'Algorithms',
  tooling: 'Tooling',
  backend_specific: 'Backend specific',
};

const TYPE_LABELS = {
  sdk_provider: 'SDK provider',
  soc: 'SoC',
  board: 'Board',
  runtime: 'Runtime',
  portable_api: 'Portable API',
  algorithm: 'Algorithm',
  tooling: 'Tooling',
  backend_specific: 'Backend specific',
};

/* One wording, used on the catalog and on every module page. The manifest is
   the only thing that says a module and a target go together, and the site is
   not allowed to upgrade that into a hardware result. */
const DECLARED_NOTE = [
  ':::note[How compatibility is declared]',
  'The boards, SoCs and toolchains listed here are the ones the module manifest declares.',
  "That is the module author's statement of intent, not evidence from hardware. Confirm on your",
  'own target before you depend on it.',
  ':::',
].join('\n');

const dirs = {
  content: path.join(siteRoot, 'src/content/docs', ROUTE),
  data: path.join(siteRoot, 'src/data'),
  public: path.join(siteRoot, 'public', ROUTE),
};

const timings = [];

function timed(label, fn) {
  const started = process.hrtime.bigint();
  const result = fn();
  timings.push({ label, ms: Math.round(Number(process.hrtime.bigint() - started) / 1e6) });
  return result;
}

/*
 * Manifest prose is another repository's words, quoted so the page agrees with
 * `nsx module describe`. Rewriting it to suit the site's American-English check
 * would make the two disagree, and helia-ui's checker has no way for a site to
 * name a generated file as quoting upstream, so the lines that carry a British
 * spelling opt out one line at a time.
 *
 * The list is explicit rather than derived, so the site's spell check still
 * fails when a manifest introduces a spelling nobody has looked at. Adding a
 * term here is the stopgap; the fix is an issue on the module's own repository.
 * The MDX escape is an expression comment and the YAML escape is a trailing
 * comment, and both are applied only where they are needed because the escape
 * itself survives into the page's Markdown rendition.
 * See tasks/256-docs-migration/helia-ui-gaps-259.md.
 */
const QUOTED_TERMS = ['serialisation']; // spelling: allow
const QUOTED_MDX = '{/* spelling: allow */}';
const QUOTED_YAML = ' # spelling: allow';

const needsEscape = (text) => {
  const lowered = String(text ?? '').toLowerCase();
  return QUOTED_TERMS.some((term) => lowered.includes(term));
};

/** Mark an emitted line as quoting a module manifest the checker would reject. */
const quoted = (line) => (needsEscape(line) ? `${line} ${QUOTED_MDX}` : line);

/** The same escape inside a JSX expression container, where it is a comment. */
const jsxEscape = (value) => (needsEscape(JSON.stringify(value)) ? ' /* spelling: allow */' : '');

/** Escape the two characters that end a cell or a row in a Markdown table. */
const cell = (value) =>
  String(value ?? '')
    .replace(/\s+/g, ' ')
    .replace(/\|/g, '\\|')
    .trim();

const list = (values) => (values && values.length ? values.join(', ') : '');

const route = (name) => `${ROUTE}/${name}`;
const href = (name) => `${BASE}${route(name)}/`;

const frontmatter = (title, description, { quotedDescription = false, extra = [] } = {}) =>
  [
    '---',
    `title: ${JSON.stringify(title)}`,
    `description: ${JSON.stringify(description)}${quotedDescription ? QUOTED_YAML : ''}`,
    ...extra,
    '---',
  ].join('\n');

function typeLabel(type) {
  return TYPE_LABELS[type] ?? type ?? 'Unclassified';
}

function facetValues(modules, pick) {
  const values = new Set();
  for (const module of modules) {
    for (const value of pick(module) ?? []) {
      if (value !== WILDCARD) values.add(value);
    }
  }
  return [...values].sort((a, b) => a.localeCompare(b));
}

function buildFacets(modules) {
  const raw = [
    {
      id: 'type',
      label: 'Type',
      values: TYPE_ORDER.filter((type) => modules.some((module) => module.type === type)).map(
        typeLabel,
      ),
    },
    { id: 'soc', label: 'SoC', values: facetValues(modules, (m) => m.compatibility.socs) },
    { id: 'board', label: 'Board', values: facetValues(modules, (m) => m.compatibility.boards) },
    {
      id: 'toolchain',
      label: 'Toolchain',
      values: facetValues(modules, (m) => m.compatibility.toolchains),
    },
    { id: 'capability', label: 'Capability', values: facetValues(modules, (m) => m.capabilities) },
  ];
  return raw
    .filter((facet) => facet.values.length > 0)
    .map((facet) => ({ ...facet, collapsed: facet.values.length > COLLAPSE_FACET_AT }));
}

function facetRows(modules) {
  const rows = {};
  for (const module of modules) {
    rows[module.name] = {
      type: [typeLabel(module.type)],
      soc: module.compatibility.socs,
      board: module.compatibility.boards,
      toolchain: module.compatibility.toolchains,
      capability: module.capabilities,
    };
  }
  return rows;
}

function catalogTable(modules) {
  const header = [
    '| Module | Type | Summary | Version | SoCs (declared) | Boards (declared) | Repo |',
    '| --- | --- | --- | --- | --- | --- | --- |',
  ];
  const rows = modules.map((module) => {
    const repo = module.source_url
      ? `[${cell(module.project)}](${module.source_url})`
      : cell(module.project);
    return [
      '',
      `[${cell(module.name)}](${href(module.name)})`,
      cell(typeLabel(module.type)),
      cell(module.summary),
      cell(module.version),
      cell(list(module.compatibility.socs)),
      cell(list(module.compatibility.boards)),
      repo,
      '',
    ]
      .join(' | ')
      .trim();
  });
  return [...header, ...rows.map(quoted)].join('\n');
}

function overviewPage(modules, boards) {
  const byType = TYPE_ORDER.map((type) => ({
    type,
    label: TYPE_GROUPS[type],
    members: modules.filter((module) => module.type === type),
  })).filter((group) => group.members.length > 0);

  const socs = new Set();
  for (const board of boards.boards) socs.add(board.soc);

  return [
    frontmatter(
      'Modules',
      'Every module the neuralSPOT-X registry pins, what it provides, and which boards, SoCs and toolchains its manifest declares.',
    ),
    '',
    "import { Card, CardGrid, LinkCard } from '@astrojs/starlight/components';",
    '',
    'An NSX app is a thin project plus the modules it depends on. The registry pins each module to',
    'a project and a revision, and every module ships an `nsx-module.yaml` manifest declaring its',
    'type, what it provides, what it depends on, and which boards, SoCs and toolchains it is',
    'compatible with. These pages are generated from exactly that data, so they report what',
    '`nsx module list` and `nsx module describe` report.',
    '',
    `The registry pins **${modules.length} modules** across **${byType.length} types**, and NSX ships`,
    `**${boards.boards.length} board descriptors** covering **${socs.size} SoCs**.`,
    '',
    DECLARED_NOTE,
    '',
    '## Start here',
    '',
    '<CardGrid>',
    `  <LinkCard title="Catalog" href="${BASE}${ROUTE}/catalog/" description="Every module in one filterable table: type, SoC, board, toolchain, capability and free text." />`,
    `  <LinkCard title="Board matrix" href="${BASE}${ROUTE}/boards/" description="Every board descriptor NSX ships, with its SoC, tier, SDK provider, CPU and toolchains." />`,
    `  <LinkCard title="nsx module" href="${BASE}reference/cli/module/" description="The commands that read this same data on your machine." />`,
    '</CardGrid>',
    '',
    '## Module types',
    '',
    'Every module declares one type. The type is what decides where a module sits in an app: a',
    'board or SoC module supplies a target, an SDK provider supplies the vendor SDK, and the rest',
    'are the libraries an app actually calls.',
    '',
    '<CardGrid>',
    ...byType.map(
      (group) =>
        `  <LinkCard title="${group.label}" href="${BASE}${ROUTE}/catalog/?type=${encodeURIComponent(typeLabel(group.type))}" description="${group.members.length} module${group.members.length === 1 ? '' : 's'}: ${group.members
          .slice(0, 4)
          .map((module) => module.name)
          .join(', ')}${group.members.length > 4 ? ' and more' : ''}." />`,
    ),
    '</CardGrid>',
    '',
    '## Adding a module',
    '',
    'Every module page carries the command that adds it to an app, and `nsx` resolves the',
    'dependency closure from the same manifests:',
    '',
    '```bash',
    'nsx module add nsx-audio',
    '```',
    '',
    `The snapshot the pages are built from is published at [\`${BASE}${ROUTE}/catalog.json\`](${BASE}${ROUTE}/catalog.json).`,
    '',
  ].join('\n');
}

function catalogPage(modules) {
  return [
    frontmatter(
      'Module catalog',
      `All ${modules.length} modules the neuralSPOT-X registry pins, filterable by type, SoC, board, toolchain and capability.`,
    ),
    '',
    "import ModuleCatalogFilter from '../../../components/ModuleCatalogFilter.tsx';",
    "import catalogFacets from '../../../data/modules-facets.json';",
    '',
    `The registry pins ${modules.length} modules. Every row below is in the page whether the filter`,
    'runs or not, so search, the Markdown rendition and an agent reading the HTML all see the full',
    'catalog. Each module name links to its own page.',
    '',
    DECLARED_NOTE,
    '',
    'A `*` in the SoC, board or toolchain column means the manifest declares every target of that',
    'kind rather than a list, and a row carrying it matches whatever you filter by.',
    '',
    '<ModuleCatalogFilter',
    '  client:only="react"',
    '  facets={catalogFacets.facets}',
    '  rows={catalogFacets.rows}',
    '  tableId="module-catalog"',
    '/>',
    '',
    '<div id="module-catalog">',
    '',
    catalogTable(modules),
    '',
    '</div>',
    '',
    `The same data is published as JSON at [\`${BASE}${ROUTE}/catalog.json\`](${BASE}${ROUTE}/catalog.json).`,
    '',
  ].join('\n');
}

function boardsPage(boards, modules) {
  const rows = boards.boards.map((board) =>
    [
      '',
      `\`${board.name}\``,
      board.soc,
      board.tier,
      board.sdk_provider,
      board.cpu.core,
      board.cpu.abi,
      list(board.toolchains),
      '',
    ]
      .join(' | ')
      .trim(),
  );

  const families = Object.entries(boards.soc_families).map(([soc, family]) =>
    [
      '',
      soc,
      family.provider ? `\`${family.provider}\`` : '',
      family.project ?? '',
      family.revision ?? '',
      cell(list(family.modules)),
      '',
    ]
      .join(' | ')
      .trim(),
  );

  const boardModules = modules.filter((module) => module.type === 'board');

  return [
    frontmatter(
      'Board matrix',
      `The ${boards.boards.length} board descriptors neuralSPOT-X ships, with the SoC, tier, SDK provider, CPU and toolchains each one declares.`,
    ),
    '',
    `NSX ships ${boards.boards.length} board descriptors. Each one is a \`board.yaml\` in the package,`,
    'and the order below is the order `nsx board list` uses.',
    '',
    DECLARED_NOTE,
    '',
    '## Boards',
    '',
    '| Board | SoC | Tier | SDK provider | CPU | ABI | Toolchains |',
    '| --- | --- | --- | --- | --- | --- | --- |',
    ...rows,
    '',
    '## SoC families',
    '',
    'The registry groups SoCs into families. A family names the SDK provider module and the project',
    'revision the family is pinned to, and the modules an app on that family resolves by default.',
    '',
    '| SoC | Provider module | Project | Revision | Family modules |',
    '| --- | --- | --- | --- | --- |',
    ...families,
    '',
    '## Board modules',
    '',
    `Each board is also a module, so an app depends on its board the same way it depends on`,
    `anything else. The registry pins ${boardModules.length} of them:`,
    '',
    ...boardModules.map((module) => `- [\`${module.name}\`](${href(module.name)})`),
    '',
  ].join('\n');
}

function section(title, lines) {
  if (!lines.length) return [];
  return [`## ${title}`, '', ...lines, ''];
}

function bullets(values) {
  return (values ?? []).map((value) => quoted(`- ${value}`));
}

function pairs(object) {
  return Object.entries(object ?? {}).map(([key, value]) =>
    quoted(`- \`${key}\`: ${typeof value === 'object' ? `\`${JSON.stringify(value)}\`` : value}`),
  );
}

function modulePage(module, known) {
  const declared = module.manifest_source !== 'unavailable';
  const description = module.summary
    ? cell(module.summary).slice(0, 160)
    : `What the ${module.name} module declares: type, dependencies and the boards, SoCs and toolchains in its manifest.`;

  const depends = (names) =>
    names.map((name) =>
      known.has(name) ? `- [\`${name}\`](${href(name)})` : `- \`${name}\``,
    );

  const exampleRefs = (module.example_refs ?? []).map((ref) =>
    quoted(typeof ref === 'string' ? `- ${ref}` : `- \`${JSON.stringify(ref)}\``),
  );

  return [
    frontmatter(module.name, description, { quotedDescription: needsEscape(description) }),
    '',
    "import ModuleCard from '../../../components/ModuleCard.astro';",
    '',
    /* Every prop is an expression container rather than a quoted attribute:
       a summary may contain a double quote, which JSX has no escape for. */
    '<ModuleCard',
    `  name={${JSON.stringify(module.name)}}`,
    `  typeLabel={${JSON.stringify(typeLabel(module.type))}}`,
    `  version={${JSON.stringify(module.version ?? '')}}`,
    `  summary={${JSON.stringify(module.summary ?? '')}${jsxEscape(module.summary)}}`,
    `  project={${JSON.stringify(module.project)}}`,
    `  revision={${JSON.stringify(module.revision)}}`,
    `  sourceUrl={${JSON.stringify(module.source_url ?? '')}}`,
    `  capabilities={${JSON.stringify(module.capabilities ?? [])}${jsxEscape(module.capabilities)}}`,
    '/>',
    '',
    ...(declared
      ? []
      : [
          ':::caution[No manifest in this snapshot]',
          `The snapshot could not read this module's \`nsx-module.yaml\`: ${cell(module.manifest_error)}.`,
          'Only the registry entry is shown below.',
          ':::',
          '',
        ]),
    '## Add it to an app',
    '',
    '```bash',
    `nsx module add ${module.name}`,
    '```',
    '',
    ...section('Capabilities', bullets(module.capabilities)),
    ...section('Use cases', bullets(module.use_cases)),
    ...section('What it is not for', bullets(module.anti_use_cases)),
    ...section('Provides', pairs(module.provides)),
    ...section('Requires', depends(module.depends.required)),
    ...section('Optional dependencies', depends(module.depends.optional)),
    '## Compatibility',
    '',
    DECLARED_NOTE,
    '',
    '| Kind | Declared |',
    '| --- | --- |',
    `| Boards | ${cell(list(module.compatibility.boards)) || 'none declared'} |`,
    `| SoCs | ${cell(list(module.compatibility.socs)) || 'none declared'} |`,
    `| Toolchains | ${cell(list(module.compatibility.toolchains)) || 'none declared'} |`,
    '',
    ...section('Constraints', pairs(module.constraints)),
    ...section('Integrations', pairs(module.integrations)),
    ...section('Examples', exampleRefs),
    ...section(
      'Agent keywords',
      [(module.agent_keywords ?? []).map((k) => `\`${k}\``).join(', ')].filter(Boolean).map(quoted),
    ),
    '## Source',
    '',
    `| Field | Value |`,
    `| --- | --- |`,
    `| Type | ${cell(typeLabel(module.type))} |`,
    `| Version | ${cell(module.version) || 'not declared'} |`,
    `| Project | ${cell(module.project)} |`,
    `| Revision | \`${cell(module.revision)}\` |`,
    `| Manifest | \`${cell(module.metadata_path)}\` |`,
    `| Repository | ${module.source_url ? `[${cell(module.project)}](${module.source_url})` : 'not published'} |`,
    '',
    `Back to the [module catalog](${BASE}${ROUTE}/catalog/).`,
    '',
  ].join('\n');
}

function sidebar(modules) {
  const items = [
    { label: 'Overview', slug: ROUTE },
    { label: 'Catalog', slug: `${ROUTE}/catalog` },
    { label: 'Board matrix', slug: `${ROUTE}/boards` },
  ];
  for (const type of TYPE_ORDER) {
    const members = modules
      .filter((module) => module.type === type)
      .sort((a, b) => a.name.localeCompare(b.name));
    if (!members.length) continue;
    items.push({
      label: TYPE_GROUPS[type],
      collapsed: true,
      items: members.map((module) => ({ label: module.name, slug: route(module.name) })),
    });
  }
  const unclassified = modules.filter((module) => !TYPE_ORDER.includes(module.type));
  if (unclassified.length) {
    items.push({
      label: 'Unclassified',
      collapsed: true,
      items: unclassified.map((module) => ({ label: module.name, slug: route(module.name) })),
    });
  }
  return items;
}

function main() {
  // CI generates the section once, as its own timed step, then runs check and
  // build, both of which would otherwise regenerate it through prepare:docs.
  if (process.env.NSX_DOCS_MODULES_PREBUILT === '1') {
    if (fs.existsSync(path.join(dirs.data, 'modules-report.json'))) {
      console.log('modules: already generated for this job, skipping regeneration.');
      return;
    }
    console.log('modules: NSX_DOCS_MODULES_PREBUILT is set but no report exists, generating.');
  }

  const snapshot = JSON.parse(
    fs.readFileSync(path.join(dirs.data, 'modules.json'), 'utf8'),
  );
  const boards = JSON.parse(fs.readFileSync(path.join(dirs.data, 'boards.json'), 'utf8'));
  const modules = [...snapshot.modules].sort((a, b) => a.name.localeCompare(b.name));
  const known = new Set(modules.map((module) => module.name));

  fs.rmSync(dirs.content, { recursive: true, force: true });
  fs.mkdirSync(dirs.content, { recursive: true });
  fs.mkdirSync(dirs.public, { recursive: true });

  const facets = buildFacets(modules);
  const rows = facetRows(modules);
  fs.writeFileSync(
    path.join(dirs.data, 'modules-facets.json'),
    `${JSON.stringify({ facets, rows }, null, 2)}\n`,
    'utf8',
  );

  timed('render pages', () => {
    fs.writeFileSync(path.join(dirs.content, 'index.mdx'), overviewPage(modules, boards), 'utf8');
    fs.writeFileSync(path.join(dirs.content, 'catalog.mdx'), catalogPage(modules), 'utf8');
    fs.writeFileSync(path.join(dirs.content, 'boards.mdx'), boardsPage(boards, modules), 'utf8');
    for (const module of modules) {
      fs.writeFileSync(
        path.join(dirs.content, `${module.name}.mdx`),
        modulePage(module, known),
        'utf8',
      );
    }
  });

  timed('publish artifacts', () => {
    fs.copyFileSync(
      path.join(dirs.data, 'modules.json'),
      path.join(dirs.public, 'catalog.json'),
    );
    fs.copyFileSync(path.join(dirs.data, 'boards.json'), path.join(dirs.public, 'boards.json'));
  });

  fs.writeFileSync(
    path.join(dirs.data, 'modules-sidebar.json'),
    `${JSON.stringify({ items: sidebar(modules) }, null, 2)}\n`,
    'utf8',
  );

  const report = {
    base: BASE,
    route: ROUTE,
    moduleCount: modules.length,
    boardCount: boards.boards.length,
    pages: modules.length + 3,
    routes: {
      overview: ROUTE,
      catalog: `${ROUTE}/catalog`,
      boards: `${ROUTE}/boards`,
    },
    modules: modules.map((module) => ({
      name: module.name,
      route: route(module.name),
      type: module.type,
      manifestSource: module.manifest_source,
    })),
    boards: boards.boards.map((board) => board.name),
    facets: facets.map((facet) => ({ id: facet.id, values: facet.values.length })),
    artifacts: {
      catalog: `${ROUTE}/catalog.json`,
      boards: `${ROUTE}/boards.json`,
    },
    timings,
  };
  fs.writeFileSync(
    path.join(dirs.data, 'modules-report.json'),
    `${JSON.stringify(report, null, 2)}\n`,
    'utf8',
  );

  const total = timings.reduce((sum, entry) => sum + entry.ms, 0);
  const withoutManifest = modules.filter((module) => module.manifest_source === 'unavailable');
  console.log(
    `modules: ${modules.length} modules on ${report.pages} pages, ${boards.boards.length} boards, ` +
      `${facets.length} facets` +
      (withoutManifest.length ? `, ${withoutManifest.length} without a manifest` : '') +
      `, ${total} ms total.`,
  );

  if (process.env.GITHUB_STEP_SUMMARY) {
    fs.appendFileSync(
      process.env.GITHUB_STEP_SUMMARY,
      [
        '### Modules generation',
        '',
        '| Stage | Duration |',
        '| --- | --- |',
        ...timings.map((entry) => `| ${entry.label} | ${entry.ms} ms |`),
        `| **total** | **${total} ms** |`,
        '',
        '| Measure | Value |',
        '| --- | --- |',
        `| Modules | ${modules.length} |`,
        `| Boards | ${boards.boards.length} |`,
        `| Pages | ${report.pages} |`,
        `| Modules with no manifest | ${withoutManifest.length} |`,
        '',
        '',
      ].join('\n'),
    );
  }
}

main();
