// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Render the CLI reference from the argparse dump produced by
 * scripts/docs/dump_cli.py.
 *
 * One page per registered command and subcommand, including the aliases, so
 * that anything `nsx --help` lists is reachable by URL. Generated content is
 * the usage line plus the argument tables; the hand-written prose that
 * survived the MkDocs site lives in reference-notes/cli/<slug>.md and is
 * merged in as a trailing notes block. A command with no notes file renders
 * with generated content only.
 */

import fs from 'node:fs';
import path from 'node:path';

const REF_IMPORTS = [
  "import RefParams from '@ambiqai/helia-ui/astro/RefParams';",
  "import RefSection from '@ambiqai/helia-ui/astro/RefSection';",
].join('\n');

/** MDX treats `{` and `<` as syntax, so generated prose has to escape them. */
function escapeMdx(text) {
  return String(text ?? '').replace(/([{}<>])/g, '\\$1');
}

function yamlString(text) {
  return JSON.stringify(String(text ?? ''));
}

function optionLabel(argument) {
  if (argument.positional) return argument.metavar || argument.name;
  const flags = argument.flags.join(', ');
  if (!argument.takes_value) return flags;
  return `${flags} ${argument.metavar || argument.name.replace(/^--/, '').toUpperCase()}`;
}

function optionType(argument) {
  if (!argument.takes_value) return 'flag';
  if (argument.choices?.length) return argument.choices.join(' | ');
  if (argument.repeatable) return 'repeatable';
  return 'value';
}

/**
 * What goes in the Default column. Only a genuine default belongs there:
 * "required" is a property of the argument, not a value, and an argument that
 * may simply be left out has neither.
 */
function defaultCell(argument) {
  if (argument.default !== null && argument.default !== undefined) return argument.default;
  if (argument.required) return 'required';
  return 'optional';
}

function describe(argument) {
  const help = argument.help ?? '';
  if (!argument.exclusive_with?.length) return help;
  const others = argument.exclusive_with.map((flag) => `\`${flag}\``).join(', ');
  return `${help}${help.endsWith('.') || !help ? '' : '.'} Cannot be combined with ${others}.`;
}

function rows(args) {
  return args.map((argument) => ({
    name: optionLabel(argument),
    type: optionType(argument),
    default: defaultCell(argument),
    description: describe(argument),
  }));
}

function refParams(caption, args) {
  if (!args.length) return '';
  const props = JSON.stringify(rows(args));
  return `<RefParams caption=${yamlString(caption)} density="compact" nameLabel="Option" typeLabel="Value" defaultLabel="Default" descriptionLabel="Description" rows={${props}} />`;
}

function sectionId(slug, suffix) {
  return `nsx-${slug}-${suffix}`;
}

/** Collect every command and subcommand node in the tree, depth first. */
export function flatten(cli) {
  const out = [];
  const visit = (node) => {
    out.push(node);
    for (const child of node.subcommands ?? []) visit(child);
  };
  for (const command of cli.commands) visit(command);
  return out;
}

export function routeFor(node, routePrefix) {
  return `${routePrefix}/${node.slug}`;
}

function renderNode(node, { cli, routePrefix, base, notes }) {
  const title = `nsx ${node.name}`;
  const summary = node.help || node.description || '';
  const lines = [
    '---',
    `title: ${yamlString(title)}`,
    `description: ${yamlString(summary || `Reference for ${title}.`)}`,
    '---',
    '',
    REF_IMPORTS,
    '',
  ];

  if (node.alias_of) {
    const target = cli.commands
      .concat(flatten(cli))
      .find((candidate) => candidate.name === node.alias_of);
    const href = target ? `${base}${routeFor(target, routePrefix)}/` : '';
    lines.push(
      `\`nsx ${node.name}\` is an alias for [\`nsx ${node.alias_of}\`](${href}). It parses the`,
      'same arguments and runs the same handler; the options below are repeated here so the',
      'alias is documented where a reader lands on it.',
      '',
    );
  } else if (node.description && node.description !== node.help) {
    lines.push(escapeMdx(node.description), '');
  } else if (summary) {
    lines.push(escapeMdx(summary), '');
  }

  lines.push(
    `<RefSection title="Usage" id=${yamlString(sectionId(node.slug, 'usage'))}>`,
    '',
    '```text',
    node.usage,
    '```',
    '',
    '</RefSection>',
    '',
  );

  const positionals = node.arguments.filter((argument) => argument.positional);
  const options = node.arguments.filter((argument) => !argument.positional);

  if (positionals.length) {
    lines.push(
      `<RefSection title="Arguments" id=${yamlString(sectionId(node.slug, 'arguments'))}>`,
      '',
      refParams('Positional arguments', positionals),
      '',
      '</RefSection>',
      '',
    );
  }

  if (options.length) {
    lines.push(
      `<RefSection title="Options" id=${yamlString(sectionId(node.slug, 'options'))}>`,
      '',
      refParams(`Options for ${title}`, options),
      '',
      '</RefSection>',
      '',
    );
  }

  if (node.subcommands?.length) {
    lines.push(
      `<RefSection title="Subcommands" id=${yamlString(sectionId(node.slug, 'subcommands'))}>`,
      '',
    );
    for (const child of node.subcommands) {
      const href = `${base}${routeFor(child, routePrefix)}/`;
      lines.push(`- [\`nsx ${child.name}\`](${href}) ${escapeMdx(child.help ?? '')}`);
    }
    lines.push('', '</RefSection>', '');
  }

  if (notes) {
    lines.push(
      `<RefSection title="Notes" id=${yamlString(sectionId(node.slug, 'notes'))}>`,
      '',
      notes.trim(),
      '',
      '</RefSection>',
      '',
    );
  }

  if (cli.global_arguments.length && !node.alias_of) {
    const flags = cli.global_arguments.map((argument) => argument.flags.join('/'));
    lines.push(
      `\`${flags.join('`, `')}\` are parsed by \`nsx\` itself, so they go before the command`,
      `name, as \`nsx -v ${node.name}\`.`,
      '',
    );
  }

  return `${lines.join('\n')}\n`;
}

function renderIndex(cli, { routePrefix, base }) {
  const distinct = cli.commands.filter((command) => !command.alias_of);
  const lines = [
    '---',
    'title: "CLI reference"',
    'description: "Every nsx command and subcommand, with its options, defaults and usage, generated from the parser."',
    '---',
    '',
    'Every page below is generated from the `nsx` argument parser, so it describes the',
    'version of NSX you installed. `nsx <command> --help` prints the same information at',
    'the terminal, and `nsx commands --json` returns the whole tree as JSON.',
    '',
    '## Commands',
    '',
  ];
  for (const command of distinct) {
    lines.push(`- [\`nsx ${command.name}\`](${base}${routeFor(command, routePrefix)}/) ${escapeMdx(command.help ?? '')}`);
  }
  lines.push('', '## Aliases', '');
  for (const [alias, target] of Object.entries(cli.aliases)) {
    const node = cli.commands.find((command) => command.name === alias);
    lines.push(
      `- [\`nsx ${alias}\`](${base}${routeFor(node, routePrefix)}/) runs \`nsx ${target}\`.`,
    );
  }
  lines.push('');
  return `${lines.join('\n')}\n`;
}

export function renderCli({ cli, outDir, notesDir, routePrefix, base }) {
  const nodes = flatten(cli);
  const pages = [];

  // Slugs already encode the command path (`module add` -> `module-add`), so
  // the pages stay flat and every route is one segment under the prefix.
  const writePage = (route, body) => {
    const file = path.join(outDir, `${path.basename(route)}.mdx`);
    fs.writeFileSync(file, body, 'utf8');
    return file;
  };

  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'index.mdx'), renderIndex(cli, { routePrefix, base }), 'utf8');
  pages.push({ route: routePrefix, name: 'index', file: path.join(outDir, 'index.mdx') });

  let merged = 0;
  for (const node of nodes) {
    const notesFile = path.join(notesDir, `${node.slug}.md`);
    let notes = null;
    if (fs.existsSync(notesFile)) {
      notes = fs.readFileSync(notesFile, 'utf8');
      merged += 1;
    }
    const body = renderNode(node, { cli, routePrefix, base, notes });
    const file = writePage(routeFor(node, routePrefix), body);
    pages.push({
      route: routeFor(node, routePrefix),
      name: node.name,
      slug: node.slug,
      aliasOf: node.alias_of ?? null,
      hasNotes: Boolean(notes),
      file,
    });
  }

  return { pages, notesMerged: merged, commandCount: nodes.length };
}

export function cliSidebar(cli, { routePrefix }) {
  const distinct = cli.commands.filter((command) => !command.alias_of);
  const items = [{ label: 'Overview', slug: routePrefix }];
  for (const command of distinct) {
    if (command.subcommands?.length) {
      items.push({
        label: `nsx ${command.name}`,
        collapsed: true,
        items: [
          { label: 'Overview', slug: routeFor(command, routePrefix) },
          ...command.subcommands.map((child) => ({
            label: `nsx ${child.name}`,
            slug: routeFor(child, routePrefix),
          })),
        ],
      });
    } else {
      items.push({ label: `nsx ${command.name}`, slug: routeFor(command, routePrefix) });
    }
  }
  items.push({
    label: 'Aliases',
    collapsed: true,
    items: Object.keys(cli.aliases).map((alias) => ({
      label: `nsx ${alias}`,
      slug: routeFor(
        cli.commands.find((command) => command.name === alias),
        routePrefix,
      ),
    })),
  });
  return items;
}
