// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
/**
 * Render the configuration reference from scripts/docs/config_schema.yaml.
 *
 * Three of the four loaders validate imperatively, so the field tables cannot
 * be introspected out of the code and live in the manifest instead.
 * tests/test_reference_generation.py is what keeps the manifest honest; this
 * module only turns it into pages.
 */

import fs from 'node:fs';
import path from 'node:path';

function yamlString(text) {
  return JSON.stringify(String(text ?? ''));
}

function escapeMdx(text) {
  return String(text ?? '').replace(/([{}<>])/g, '\\$1');
}

// RefParams gives four columns, so required-ness rides in the type cell and
// the default column holds only actual defaults. A field that is required in
// some documents carries the condition rather than a bare "required".
function typeCell(field) {
  const base = field.values ? `${field.type} (${field.values})` : field.type;
  if (!field.required) return base;
  return field.required_when ? `${base}, required when ${field.required_when}` : `${base}, required`;
}

/* Exported for the agent bundle, as in render-cli.mjs. */
export function rows(fields) {
  return fields.map((field) => ({
    name: field.path,
    type: typeCell(field),
    default: field.default ?? '',
    description: field.description ?? '',
  }));
}

function renderSchema(schema) {
  const lines = [
    '---',
    `title: ${yamlString(schema.title)}`,
    `description: ${yamlString(schema.summary.trim())}`,
    '---',
    '',
    "import RefParams from '@ambiqai/helia-ui/astro/RefParams';",
    "import RefSection from '@ambiqai/helia-ui/astro/RefSection';",
    '',
    escapeMdx(schema.summary.trim()),
    '',
    `<RefSection title="Fields" id=${yamlString(`${schema.id}-fields`)}>`,
    '',
    `<RefParams caption=${yamlString(`${schema.file} fields`)} density="compact" nameLabel="Field" typeLabel="Type" defaultLabel="Default" descriptionLabel="Meaning" rows={${JSON.stringify(rows(schema.fields))}} />`,
    '',
    '</RefSection>',
    '',
    `<RefSection title="Example" id=${yamlString(`${schema.id}-example`)}>`,
    '',
    '```yaml',
    schema.example.trimEnd(),
    '```',
    '',
    '</RefSection>',
    '',
    `<RefSection title="How it is read" id=${yamlString(`${schema.id}-loader`)}>`,
    '',
    `NSX reads \`${schema.file}\` through \`${schema.loader}\`, which raises`,
    `\`${schema.error}\` when the document is invalid. The supported`,
    `\`schema_version\` is \`${schema.schema_version}\`.`,
    '',
    `**Unknown keys:** ${escapeMdx(schema.unknown_keys.trim())}`,
    '',
    '</RefSection>',
    '',
  ];
  return `${lines.join('\n')}\n`;
}

function renderIndex(schemas, { routePrefix, base }) {
  const lines = [
    '---',
    'title: "Configuration reference"',
    'description: "The schema of every file NSX reads: the app manifest, module metadata, board descriptors and the resolution lock."',
    '---',
    '',
    'NSX reads four files. Three you write, one it writes for you.',
    '',
  ];
  for (const schema of schemas) {
    lines.push(
      `- [\`${schema.file}\`](${base}${routePrefix}/${schema.id}/) ${escapeMdx(schema.summary.trim().replace(/\s+/g, ' '))}`,
    );
  }
  lines.push(
    '',
    'Each table is checked against the loader by a test, so a field that changes in the',
    'code and not here fails the build rather than going quietly stale.',
    '',
  );
  return `${lines.join('\n')}\n`;
}

export function renderConfig({ manifest, outDir, routePrefix, base }) {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, 'index.mdx'),
    renderIndex(manifest.schemas, { routePrefix, base }),
    'utf8',
  );
  const pages = [{ route: routePrefix, name: 'index' }];
  for (const schema of manifest.schemas) {
    fs.writeFileSync(
      path.join(outDir, `${schema.id}.mdx`),
      renderSchema(schema),
      'utf8',
    );
    pages.push({
      route: `${routePrefix}/${schema.id}`,
      name: schema.file,
      fields: schema.fields.length,
    });
  }
  return { pages };
}

export function configSidebar(manifest, { routePrefix }) {
  return [
    { label: 'Overview', slug: routePrefix },
    ...manifest.schemas.map((schema) => ({
      label: schema.file,
      slug: `${routePrefix}/${schema.id}`,
    })),
  ];
}
