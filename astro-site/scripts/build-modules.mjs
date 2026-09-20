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

import { TYPE_GROUPS, TYPE_ORDER, typeLabel } from './lib/module-types.mjs';

const siteRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

const BASE = '/neuralspotx/';
const ROUTE = 'modules';

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

/* Where the committed snapshot is read from. Only the input moves:
   scripts/test-modules-escaping.mjs points it at a fixture carrying the
   payloads a manifest can carry, so the pages it inspects come out of this
   site's own build rather than a scratch imitation of it. */
const snapshotDir = process.env.NSX_DOCS_MODULES_SNAPSHOT
  ? path.resolve(process.env.NSX_DOCS_MODULES_SNAPSHOT)
  : dirs.data;

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
/* An empty inline element rather than an MDX comment: the checker reads the
   line the mark sits on, the page renders nothing for it, and the rendition
   writer drops tags, so the marked cell and the marked bullet are still a
   cell and a bullet in the page's markdown rendition. */
const QUOTED_MARK = '<span data-quoted="spelling: allow" />';
const QUOTED_YAML = ' # spelling: allow';

const needsEscape = (value) => {
  const lowered = String(value ?? '').toLowerCase();
  return QUOTED_TERMS.some((term) => lowered.includes(term));
};

/** The same mark inside a JSX expression container, where it is a comment. */
const jsxEscape = (value) => (needsEscape(JSON.stringify(value)) ? ' /* spelling: allow */' : '');

const collapse = (value) => String(value ?? '').replace(/\s+/g, ' ').trim();

/*
 * Every string that comes out of a manifest goes through one of the three
 * helpers below before it reaches the page, because the page is MDX and the
 * manifest is another repository's file.
 *
 * In MDX a `<` opens a tag, a `{` opens an expression the build evaluates, a
 * backtick opens a code span and a `|` ends a table cell. A summary nobody
 * here writes reaches all four: an unclosed attribute fails the build, and
 * anything that parsed as a tag would reach the reader as markup rather than
 * as the text the manifest declares.
 *
 * Angle brackets become character references and the rest take a backslash.
 * Both render as the character the manifest wrote, but the markdown rendition
 * is produced by dropping anything shaped like a tag, and a backslash in front
 * of one does not stop it being dropped: `\<img src=x\>` would reach the
 * rendition as a lone backslash. An entity is not that shape, so the text
 * survives the trip.
 */
const escape = (value) =>
  String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/[\\`{}|]/g, (char) => `\\${char}`);

const mark = (source, rendered) =>
  needsEscape(source) && rendered ? `${rendered} ${QUOTED_MARK}` : rendered;

/** Manifest prose as text: one line, escaped, marked when it quotes upstream. */
const text = (value) => {
  const one = collapse(value);
  return mark(one, escape(one));
};

/*
 * Manifest prose as an inline code span. Markdown code carries no MDX
 * expressions and no JSX, so the span itself is the escape; the fence grows
 * past the longest run of backticks in the value, which is the rule CommonMark
 * gives for the same problem, and a value that starts or ends with a backtick
 * is padded so the fence still closes where it should.
 */
const code = (value) => {
  const one = collapse(value);
  if (!one) return '';
  const runs = [...one.matchAll(/`+/g)].map((match) => match[0].length);
  const fence = '`'.repeat(Math.max(0, ...runs) + 1);
  const pad = one.startsWith('`') || one.endsWith('`') ? ' ' : '';
  return mark(one, `${fence}${pad}${one}${pad}${fence}`);
};

/* A pipe inside a code span still ends the cell, and GFM reads the escape
   through the span; outside a table the backslash would be literal, so only
   the cells pay for it. */
const codeCell = (value) => code(value).replace(/\|/g, '\\|');

/* A markdown destination ends at a space or a bracket. The registry's URLs
   carry neither, and this is what keeps that true when one does. */
const target = (value) => encodeURI(String(value ?? '')).replace(/[()<>]/g, encodeURIComponent);

const link = (label, url) => `[${label}](${target(url)})`;

/*
 * A page description leaves MDX behind: Starlight writes it into a meta
 * attribute, where a quotation mark is escaped for us, and helia-ui's
 * discoverability block writes it into a JSON-LD script, where nothing is --
 * a manifest summary carrying `</script>` would end that block and the rest of
 * it would be markup. This site writes neither emitter, so the characters that
 * can end one are dropped from a description rather than escaped for whichever
 * context it lands in. See tasks/256-docs-migration/helia-ui-gaps-259.md.
 */
const metaText = (value) => collapse(value).replace(/[<>]/g, '');

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

function catalogTable(modules) {
  const header = [
    '| Module | Type | Summary | Version | SoCs (declared) | Boards (declared) | Repo |',
    '| --- | --- | --- | --- | --- | --- | --- |',
  ];
  const rows = modules.map((module) => {
    const repo = module.source_url
      ? link(text(module.project), module.source_url)
      : text(module.project);
    return [
      '',
      link(text(module.name), href(module.name)),
      text(typeLabel(module.type)),
      text(module.summary),
      text(module.version),
      text(list(module.compatibility.socs)),
      text(list(module.compatibility.boards)),
      repo,
      '',
    ]
      .join(' | ')
      .trim();
  });
  return [...header, ...rows].join('\n');
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
    /* Props as expression containers, not quoted attributes: the description
       carries module names, and a quoted attribute has no escape for a
       quotation mark the way a JSON string does. */
    ...byType.map((group) => {
      const names = group.members
        .slice(0, 4)
        .map((module) => module.name)
        .join(', ');
      const description =
        `${group.members.length} module${group.members.length === 1 ? '' : 's'}: ` +
        `${names}${group.members.length > 4 ? ' and more' : ''}.`;
      const url = `${BASE}${ROUTE}/catalog/?type=${encodeURIComponent(typeLabel(group.type))}`;
      return (
        `  <LinkCard title={${JSON.stringify(group.label)}} href={${JSON.stringify(url)}} ` +
        `description={${JSON.stringify(description)}${jsxEscape(description)}} />`
      );
    }),
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
    "import ModuleIndex from '../../../components/ModuleIndex.astro';",
    '',
    `The registry pins ${modules.length} modules. Search and the chips below filter the list; the`,
    'same modules are in the page as a table whether the filter runs or not, so the Markdown',
    'rendition and an agent reading the HTML see the full catalog either way. Each module name',
    'links to its own page.',
    '',
    DECLARED_NOTE,
    '',
    'A module whose manifest declares every target of a kind rather than a list carries **any** in',
    'that facet, and the table below shows the `*` the manifest writes.',
    '',
    `<ModuleIndex base={${JSON.stringify(BASE)}} tableId="module-catalog" />`,
    '',
    '<div id="module-catalog">',
    '',
    '## All modules',
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
      codeCell(board.name),
      text(board.soc),
      text(board.tier),
      text(board.sdk_provider),
      text(board.cpu.core),
      text(board.cpu.abi),
      text(list(board.toolchains)),
      '',
    ]
      .join(' | ')
      .trim(),
  );

  const families = Object.entries(boards.soc_families).map(([soc, family]) =>
    [
      '',
      text(soc),
      family.provider ? codeCell(family.provider) : '',
      text(family.project ?? ''),
      text(family.revision ?? ''),
      text(list(family.modules)),
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
    ...boardModules.map((module) => `- ${link(code(module.name), href(module.name))}`),
    '',
  ].join('\n');
}

function section(title, lines) {
  if (!lines.length) return [];
  return [`## ${title}`, '', ...lines, ''];
}

function bullets(values) {
  return (values ?? []).map((value) => `- ${text(value)}`);
}

function pairs(object) {
  return Object.entries(object ?? {}).map(([key, value]) => {
    const rendered =
      value !== null && typeof value === 'object' ? code(JSON.stringify(value)) : text(value);
    return `- ${code(key)}: ${rendered}`;
  });
}

function modulePage(module, known, uncheckedProjects) {
  const declared = module.manifest_source !== 'unavailable';
  const description = module.summary
    ? metaText(module.summary).slice(0, 160)
    : `What the ${module.name} module declares: type, dependencies and the boards, SoCs and toolchains in its manifest.`;

  const depends = (names) =>
    names.map((name) => (known.has(name) ? `- ${link(code(name), href(name))}` : `- ${code(name)}`));

  const exampleRefs = (module.example_refs ?? []).map((ref) =>
    typeof ref === 'string' ? `- ${text(ref)}` : `- ${code(JSON.stringify(ref))}`,
  );

  /* The snapshot names the projects the public build is not expected to read
     again, so a reader is told which page carries fields nothing re-checked.
     Driven by that list: it goes when the list does. */
  const unchecked = uncheckedProjects?.[module.project];

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
          `The snapshot could not read this module's \`nsx-module.yaml\`: ${text(module.manifest_error)}.`,
          'Only the registry entry is shown below.',
          ':::',
          '',
        ]),
    ...(unchecked
      ? [
          ':::note[Read from a private repository]',
          `${code(module.project)} is ${text(unchecked)}.`,
          'This page carries the fields the committed snapshot recorded, and the public docs',
          'build does not read the manifest again.',
          ':::',
          '',
        ]
      : []),
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
    `| Boards | ${text(list(module.compatibility.boards)) || 'none declared'} |`,
    `| SoCs | ${text(list(module.compatibility.socs)) || 'none declared'} |`,
    `| Toolchains | ${text(list(module.compatibility.toolchains)) || 'none declared'} |`,
    '',
    ...section('Constraints', pairs(module.constraints)),
    ...section('Integrations', pairs(module.integrations)),
    ...section('Examples', exampleRefs),
    ...section(
      'Agent keywords',
      [(module.agent_keywords ?? []).map((keyword) => code(keyword)).join(', ')].filter(Boolean),
    ),
    '## Source',
    '',
    `| Field | Value |`,
    `| --- | --- |`,
    `| Type | ${text(typeLabel(module.type))} |`,
    `| Version | ${text(module.version) || 'not declared'} |`,
    `| Project | ${text(module.project)} |`,
    `| Revision | ${codeCell(module.revision)} |`,
    `| Manifest | ${codeCell(module.metadata_path)} |`,
    `| Repository | ${module.source_url ? link(text(module.project), module.source_url) : 'not published'} |`,
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

  const snapshot = JSON.parse(fs.readFileSync(path.join(snapshotDir, 'modules.json'), 'utf8'));
  const boards = JSON.parse(fs.readFileSync(path.join(snapshotDir, 'boards.json'), 'utf8'));
  const modules = [...snapshot.modules].sort((a, b) => a.name.localeCompare(b.name));
  const known = new Set(modules.map((module) => module.name));

  fs.rmSync(dirs.content, { recursive: true, force: true });
  fs.mkdirSync(dirs.content, { recursive: true });
  fs.mkdirSync(dirs.public, { recursive: true });

  timed('render pages', () => {
    fs.writeFileSync(path.join(dirs.content, 'index.mdx'), overviewPage(modules, boards), 'utf8');
    fs.writeFileSync(path.join(dirs.content, 'catalog.mdx'), catalogPage(modules), 'utf8');
    fs.writeFileSync(path.join(dirs.content, 'boards.mdx'), boardsPage(boards, modules), 'utf8');
    for (const module of modules) {
      fs.writeFileSync(
        path.join(dirs.content, `${module.name}.mdx`),
        modulePage(module, known, snapshot.unchecked_projects),
        'utf8',
      );
    }
  });

  timed('publish artifacts', () => {
    fs.copyFileSync(path.join(snapshotDir, 'modules.json'), path.join(dirs.public, 'catalog.json'));
    fs.copyFileSync(path.join(snapshotDir, 'boards.json'), path.join(dirs.public, 'boards.json'));
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
    `modules: ${modules.length} modules on ${report.pages} pages, ${boards.boards.length} boards` +
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
