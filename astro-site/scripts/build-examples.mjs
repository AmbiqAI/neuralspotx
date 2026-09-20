// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/*
 * Renders the Examples pages under Guides from two sources outside this
 * directory: the front matter in `docs/examples/*.md` and the body of each
 * `examples/<name>/README.md` (AmbiqAI/neuralspotx#260).
 *
 * The READMEs are included at build time rather than imported from MDX. An
 * MDX `import { Content }` of a file outside the site root does render in the
 * HTML, but the discoverability plugin's Markdown rendition is derived from
 * the MDX source, so component-only content comes out empty and the `.md`
 * route an agent reads would carry nothing but the title.
 *
 * Output lands in src/content/docs/guides/examples/ and src/data, and is
 * gitignored: the READMEs are the source of record, so a committed copy could
 * only ever be a stale one.
 */
import { mkdir, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const siteRoot = path.resolve(import.meta.dirname, '..');
const repoRoot = path.resolve(siteRoot, '..');
const stubDir = path.join(repoRoot, 'docs', 'examples');
const exampleDir = path.join(repoRoot, 'examples');
const outDir = path.join(siteRoot, 'src', 'content', 'docs', 'guides', 'examples');
const dataDir = path.join(siteRoot, 'src', 'data');

const REPO_TREE = 'https://github.com/AmbiqAI/neuralspotx/tree/main/examples';

/* Tier order is the reading order the section presents: start simple, then
   single capabilities, then examples that compose several. */
const TIER_ORDER = ['basics', 'capabilities', 'integrations'];
const TIER_LABEL = {
  basics: 'Basics',
  capabilities: 'Capabilities',
  integrations: 'Integrations',
};

/*
 * Spellings an example author wrote that the site's American-English check
 * would otherwise reject. The READMEs are quoted verbatim, so the fix is an
 * opt-out on the line rather than an edit to someone else's file. A new
 * British spelling in a README fails `npm run validate` until it is added
 * here, which is the point: nobody's prose changes silently.
 */
const QUOTED_TERMS = [];
const QUOTED_MARKER = ' <!-- spelling: allow -->';

const fail = (message) => {
  console.error(`build-examples: ${message}`);
  process.exit(1);
};

/**
 * Minimal front matter reader for the example stubs.
 *
 * The stubs only ever carry scalars and flow-style lists, so a YAML
 * dependency would buy nothing. Anything else is an error rather than a
 * silent miss.
 */
const parseFrontMatter = (text, source) => {
  const match = /^---\n([\s\S]*?)\n---/.exec(text);
  if (!match) fail(`${source} has no front matter`);
  const out = {};
  for (const line of match[1].split('\n')) {
    if (!line.trim() || line.trimStart().startsWith('#')) continue;
    const at = line.indexOf(':');
    if (at === -1) fail(`${source}: cannot parse front matter line: ${line}`);
    const key = line.slice(0, at).trim();
    const raw = line.slice(at + 1).trim();
    out[key] = raw.startsWith('[')
      ? raw
          .slice(1, -1)
          .split(',')
          .map((v) => v.trim())
          .filter(Boolean)
      : raw.replace(/^['"]|['"]$/g, '');
  }
  return out;
};

/** Quote a value for a YAML double-quoted scalar. */
const yamlString = (value) => `"${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;

const codeList = (values) =>
  values.length ? values.map((v) => `\`${v}\``).join(', ') : 'none declared';

/**
 * Strip the README's own H1 and opt the known quoted spellings out of the
 * site's spelling check. Everything else is the author's text, unchanged.
 */
const prepareReadme = (body) => {
  const lines = body.replace(/\r\n/g, '\n').split('\n');
  while (lines.length && !lines[0].trim()) lines.shift();
  if (lines[0]?.startsWith('# ')) {
    lines.shift();
    while (lines.length && !lines[0].trim()) lines.shift();
  }
  return lines
    .map((line) => (QUOTED_TERMS.some((term) => line.includes(term)) ? line + QUOTED_MARKER : line))
    .join('\n')
    .trimEnd();
};

const main = async () => {
  const stubs = (await readdir(stubDir))
    .filter((name) => name.endsWith('.md') && name !== 'index.md')
    .sort();
  if (!stubs.length) fail(`no example stubs under ${stubDir}`);

  const examples = [];
  for (const stub of stubs) {
    const name = stub.replace(/\.md$/, '');
    const meta = parseFrontMatter(await readFile(path.join(stubDir, stub), 'utf8'), stub);
    let readme;
    try {
      readme = await readFile(path.join(exampleDir, name, 'README.md'), 'utf8');
    } catch {
      fail(`examples/${name}/README.md is missing but docs/examples/${stub} documents it`);
    }
    for (const field of ['title', 'tier', 'summary', 'status']) {
      if (!meta[field]) fail(`docs/examples/${stub} is missing '${field}'`);
    }
    if (!TIER_ORDER.includes(meta.tier)) fail(`docs/examples/${stub} has unknown tier '${meta.tier}'`);
    examples.push({
      name,
      title: meta.title,
      tier: meta.tier,
      summary: meta.summary,
      status: meta.status,
      capabilities: meta.capabilities ?? [],
      boardsTested: meta.boards_tested ?? [],
      body: prepareReadme(readme),
    });
  }

  examples.sort(
    (a, b) =>
      TIER_ORDER.indexOf(a.tier) - TIER_ORDER.indexOf(b.tier) || a.name.localeCompare(b.name),
  );

  await rm(outDir, { recursive: true, force: true });
  await mkdir(outDir, { recursive: true });

  for (const ex of examples) {
    const page = `---
title: ${yamlString(ex.title)}
description: ${yamlString(ex.summary)}
---

${ex.summary}

| Declared by the example author | Value |
| --- | --- |
| Tier | ${TIER_LABEL[ex.tier]} |
| Status | \`${ex.status}\` |
| Capabilities | ${codeList(ex.capabilities)} |
| Boards tested | ${codeList(ex.boardsTested)} |

Build it from a source checkout by name, because the positional app argument resolves
under \`./examples\`:

\`\`\`bash
nsx build ${ex.name} --board apollo510_evb
\`\`\`

The rest of this page is the example's own README, from
[\`examples/${ex.name}/\`](${REPO_TREE}/${ex.name}).

${ex.body}
`;
    await writeFile(path.join(outDir, `${ex.name}.md`), page, 'utf8');
  }

  const rows = examples
    .map(
      (ex) =>
        `| [${ex.title}](/neuralspotx/guides/examples/${ex.name}/) | ${TIER_LABEL[ex.tier]} | \`${ex.status}\` | ${codeList(ex.capabilities)} | ${codeList(ex.boardsTested)} |`,
    )
    .join('\n');

  const index = `---
title: Examples
description: The example apps this repository ships, what each one demonstrates, and the tier, status and boards their authors declare.
---

Every example here is a real NSX app: an \`nsx.yml\`, a \`CMakeLists.txt\` and source, built by
the same commands as an app you generate. They are the fastest way to see how a capability
is wired before you wire it yourself.

From a source checkout you can build any of them by name, because the positional app
argument resolves under \`./examples\`:

\`\`\`bash
nsx build hello_world --board apollo510_evb
\`\`\`

Several declare more than one target, so \`--board\` picks which one you are building. See
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/).

## What each one covers

| Example | Tier | Status | Capabilities | Boards tested |
| --- | --- | --- | --- | --- |
${rows}

Every column in that table comes from the example's own front matter. **Tier** is the
reading order: \`Basics\` first, then \`Capabilities\` one at a time, then
\`Integrations\` that compose several. **Status** and **Boards tested** are the author's
declaration of what they ran and where, not a test record this site holds, so treat a
"none declared" boards column as "not stated" rather than as "does not work".

## Where to start

- New to NSX: [Hello World](/neuralspotx/guides/examples/hello_world/), then
  [FreeRTOS Blinky](/neuralspotx/guides/examples/freertos_blinky/).
- Measuring something: [PMU Profiling](/neuralspotx/guides/examples/pmu_profiling/),
  [Power Benchmark](/neuralspotx/guides/examples/power_benchmark/) and
  [CoreMark](/neuralspotx/guides/examples/coremark/).
- Running a model: [KWS Inference](/neuralspotx/guides/examples/kws_infer/).
- Talking to a host: [USB Serial](/neuralspotx/guides/examples/usb_serial/),
  [USB RPC](/neuralspotx/guides/examples/usb_rpc/) and
  [BLE Webble](/neuralspotx/guides/examples/ble_webble/).
- Reading a sensor: [Audio Capture](/neuralspotx/guides/examples/audio_capture/).

The sources are in
[\`examples/\`](https://github.com/AmbiqAI/neuralspotx/tree/main/examples) in the
repository, and each page below carries that example's README.
`;
  await writeFile(path.join(outDir, 'index.md'), index, 'utf8');

  await mkdir(dataDir, { recursive: true });
  await writeFile(
    path.join(dataDir, 'examples-sidebar.json'),
    `${JSON.stringify(
      {
        items: [
          { label: 'Overview', slug: 'guides/examples' },
          ...examples.map((ex) => ({ label: ex.title, slug: `guides/examples/${ex.name}` })),
        ],
      },
      null,
      2,
    )}\n`,
    'utf8',
  );

  console.log(`build-examples: ${examples.length} examples on ${examples.length + 1} pages`);
};

await main();
