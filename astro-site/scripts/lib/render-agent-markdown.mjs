// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Model-derived Markdown for the routes whose content lives in component props.
 *
 * helia-ui's discoverability pass builds llms.txt, llms-full.txt and the
 * per-route `.md` renditions by reading the authored source and deleting every
 * tag. That is right for prose, and lossy for anything generated: a CLI page
 * keeps its usage block and loses its option table, a Python API page keeps the
 * module docstring and loses every signature. So the generated routes are
 * rendered here a second time, from the same models the MDX was rendered from,
 * and publish-agent-bundle.mjs swaps the results in after the build.
 *
 * Rendering from the model rather than stripping the MDX is the point: a table
 * that only ever existed as a `rows={...}` prop cannot be recovered from the
 * output, and the HTML is a view, not a source.
 */

import fs from 'node:fs';
import path from 'node:path';
import { flatten, routeFor, rows as cliRows } from './render-cli.mjs';
import { rows as configRows } from './render-config.mjs';

/** A pipe inside a cell would start a new column. */
const cell = (value) => String(value ?? '').replace(/\|/g, '\\|').replace(/\n+/g, ' ').trim();

export function table(headers, bodyRows) {
  if (bodyRows.length === 0) return '';
  return [
    `| ${headers.join(' | ')} |`,
    `| ${headers.map(() => '---').join(' | ')} |`,
    ...bodyRows.map((row) => `| ${row.map(cell).join(' | ')} |`),
  ].join('\n');
}

/*
 * MDX comments are `{/* ... *\/}` and survive the plugin's tag stripper, which
 * only removes balanced tags. They are authoring notes, not page text.
 */
const stripMdxComments = (text) => text.replace(/\{\s*\/\*[\s\S]*?\*\/\s*\}/g, '').trim();

/** Absolute URLs, because a bundle is read away from the route it came from. */
const link = (label, href, origin) => `[${label}](${origin}${href})`;

export function renderCliPageMarkdown(node, { cli, notes, routePrefix, base, origin }) {
  const title = `nsx ${node.name}`;
  const out = [`# ${title}`, ''];
  const summary = node.help || node.description || '';

  if (node.alias_of) {
    const target = flatten(cli).find((candidate) => candidate.name === node.alias_of);
    const href = target ? `${base}${routeFor(target, routePrefix)}/` : '';
    out.push(
      `\`nsx ${node.name}\` is an alias for ${link(`\`nsx ${node.alias_of}\``, href, origin)}. ` +
        'It parses the same arguments and runs the same handler.',
      '',
    );
  } else if (node.description && node.description !== node.help) {
    out.push(node.description, '');
  } else if (summary) {
    out.push(summary, '');
  }

  out.push('## Usage', '', '```text', node.usage, '```', '');

  const positionals = node.arguments.filter((argument) => argument.positional);
  const options = node.arguments.filter((argument) => !argument.positional);
  const toRow = (row) => [row.name, row.type, row.default, row.description];

  if (positionals.length) {
    out.push(
      '## Arguments',
      '',
      table(['Option', 'Value', 'Default', 'Description'], cliRows(positionals).map(toRow)),
      '',
    );
  }
  if (options.length) {
    out.push(
      '## Options',
      '',
      table(['Option', 'Value', 'Default', 'Description'], cliRows(options).map(toRow)),
      '',
    );
  }
  if (node.subcommands?.length) {
    out.push('## Subcommands', '');
    for (const child of node.subcommands) {
      out.push(
        `- ${link(`\`nsx ${child.name}\``, `${base}${routeFor(child, routePrefix)}/`, origin)} ${child.help ?? ''}`,
      );
    }
    out.push('');
  }
  if (notes) out.push('## Notes', '', stripMdxComments(notes), '');

  if (cli.global_arguments.length && !node.alias_of) {
    const flags = cli.global_arguments.map((argument) => argument.flags.join('/'));
    out.push(
      `\`${flags.join('`, `')}\` are parsed by \`nsx\` itself, so they go before the ` +
        `command name, as \`nsx -v ${node.name}\`.`,
      '',
    );
  }
  return `${out.join('\n').trimEnd()}\n`;
}

export function renderConfigPageMarkdown(schema) {
  const toRow = (row) => [row.name, row.type, row.default, row.description];
  return `${[
    `# ${schema.title}`,
    '',
    schema.summary.trim(),
    '',
    '## Fields',
    '',
    table(['Field', 'Type', 'Default', 'Meaning'], configRows(schema.fields).map(toRow)),
    '',
    '## Example',
    '',
    '```yaml',
    schema.example.trimEnd(),
    '```',
    '',
    '## How it is read',
    '',
    `NSX reads \`${schema.file}\` through \`${schema.loader}\`, which raises ` +
      `\`${schema.error}\` when the document is invalid. The supported \`schema_version\` ` +
      `is \`${schema.schema_version}\`.`,
    '',
    `**Unknown keys:** ${schema.unknown_keys.trim()}`,
  ].join('\n')}\n`;
}

/**
 * Split the pyref text bundle back into one section per module page.
 *
 * pyref publishes every module as Markdown in one file, each module opening at
 * an H1. That file is the reference model rendered by the same code that built
 * the pages, so it is the right source for the API renditions; it just has to
 * be cut at the module boundaries and keyed by route.
 */
export function splitPyrefBundle(bundleText) {
  const sections = new Map();
  let current = null;
  let fenced = false;
  for (const line of bundleText.split('\n')) {
    if (/^(```|~~~)/.test(line)) fenced = !fenced;
    const heading = !fenced && /^# (\S+)\s*$/.exec(line);
    if (heading) {
      current = { name: heading[1], lines: [line] };
      sections.set(heading[1], current);
      continue;
    }
    if (current) current.lines.push(line);
  }
  return new Map(
    [...sections].map(([name, section]) => [name, `${section.lines.join('\n').trimEnd()}\n`]),
  );
}

/**
 * The facts a module page states only through ModuleCard's props.
 *
 * The rest of a module page is already Markdown, so this is a prepend rather
 * than a re-render: version, project and revision are what an agent needs to
 * tell one pinned module from another and they exist nowhere in the rendition.
 */
export function moduleFactsMarkdown(module, { typeLabel }) {
  const lines = [];
  if (module.summary) lines.push(module.summary, '');
  lines.push(
    `- Type: ${typeLabel}`,
    `- Version: ${module.version ?? 'unversioned'}`,
    `- Project: ${module.project}`,
    `- Revision: ${module.revision}`,
  );
  if (module.source_url) lines.push(`- Source: ${module.source_url}`);
  if (module.capabilities?.length) lines.push(`- Capabilities: ${module.capabilities.join(', ')}`);
  return `${lines.join('\n')}\n`;
}

export function readNotes(notesDir, slug) {
  const file = path.join(notesDir, `${slug}.md`);
  return fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : null;
}

/**
 * The link cards an authored page carries, in the order the source writes them.
 *
 * `<LinkCard title="Catalog" href="/modules/catalog/" description="..." />` is a
 * labeled link on the page and nothing at all in the rendition: the stripper
 * removes the tag and keeps the children, so a card whose text is a prop leaves
 * an empty section behind. The props are authored data, not rendered output, so
 * reading them back recovers what the page says.
 *
 * Every card is returned, including repeats of one href, because seven cards
 * pointing at the catalog are seven different statements about it. Each carries
 * the Markdown heading it sits under, so the composer can put it back where the
 * page puts it rather than in a list at the end.
 */
export function componentCards(source) {
  const cards = [];
  const headings = [...source.matchAll(/^(#{2,6})[ \t]+(.+?)[ \t]*$/gm)];
  const headingAt = (offset) => {
    const previous = headings.filter((heading) => heading.index < offset).pop();
    return previous ? previous[2] : null;
  };
  const attribute = (chunk, name) => {
    const match = new RegExp(`\\b${name}=(?:"([^"]*)"|\\{"([^"]*)"\\})`).exec(chunk);
    return match ? (match[1] ?? match[2]) : null;
  };
  for (const match of source.matchAll(/<(LinkCard|Button|Card)\b([\s\S]*?)(\/?)>/g)) {
    const [, tag, props, selfClosing] = match;
    const href = attribute(props, 'href');
    if (!href) continue;
    const title = attribute(props, 'title');
    let description = attribute(props, 'description');
    if (!description && !selfClosing) {
      const close = source.indexOf(`</${tag}>`, match.index + match[0].length);
      if (close !== -1) {
        description = source
          .slice(match.index + match[0].length, close)
          .replace(/\s+/g, ' ')
          .trim();
      }
    }
    cards.push({
      heading: headingAt(match.index),
      href,
      title: title ?? description ?? href,
      description: title ? description : null,
    });
  }
  return cards;
}

export function cardsMarkdown(cards, { origin }) {
  return cards
    .map(({ title, href, description }) => {
      const target = href.startsWith('http') ? href : `${origin}${href}`;
      return `- [${title}](${target})${description ? `: ${description}` : ''}`;
    })
    .join('\n');
}
