// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import { heliaStarlight } from '@ambiqai/helia-ui/starlight';
import buildInfo from './src/data/build-info.json' with { type: 'json' };
// Written by scripts/build-reference.mjs, which every dev, check and build run
// invokes through prepare:docs before Astro starts.
import referenceSidebar from './src/data/reference-sidebar.json' with { type: 'json' };
// Written by scripts/build-modules.mjs from the committed module snapshot, in
// the same prepare:docs pass (AmbiqAI/neuralspotx#259).
import modulesSidebar from './src/data/modules-sidebar.json' with { type: 'json' };

const base = '/neuralspotx';
const basePath = `${base}/`;

export default defineConfig({
  site: 'https://ambiqai.github.io',
  base,
  integrations: [
    /* The module catalog's filter is the site's one island
       (src/components/ModuleCatalogFilter.tsx). */
    react(),
    starlight({
      title: 'neuralSPOT-X',
      description:
        'The single CLI that scaffolds, builds, flashes and profiles firmware for Ambiq SoCs.',
      favicon: '/neuralspotx-icon.png',
      logo: { src: './public/neuralspotx-icon.png', alt: 'neuralSPOT-X' },
      /* site-theme.css last, so its dials land on top of the package sheets
         the plugin splices in ahead of it. */
      customCss: ['./src/styles/tailwind.css', './src/styles/site-theme.css'],
      plugins: [
        heliaStarlight({
          header: {
            title: 'neuralSPOT-X',
            hub: {
              label: 'HELIA',
              href: 'https://ambiqai.github.io/helia-developer-hub/',
            },
          },
          /* Home carries no pages of its own, so it renders at the full width
             of the frame and the other four are reached from the top bar.
             Guides is still an Overview entry until its content lands in
             #260's second PR. */
          sections: [
            { label: 'Home', href: basePath, sidebar: false },
            {
              label: 'Getting started',
              href: `${basePath}getting-started/`,
              /* The three per-OS pages sit under Install rather than beside it:
                 the tabbed page is the one to read, and they exist so the old
                 MkDocs routes still land somewhere (#261). */
              sidebar: [
                { label: 'Overview', slug: 'getting-started' },
                {
                  label: 'Install',
                  collapsed: false,
                  items: [
                    { label: 'All platforms', slug: 'getting-started/install' },
                    { label: 'macOS', slug: 'getting-started/install/macos' },
                    { label: 'Linux', slug: 'getting-started/install/linux' },
                    { label: 'Windows', slug: 'getting-started/install/windows' },
                  ],
                },
                { label: 'Check your environment', slug: 'getting-started/doctor' },
                { label: 'Create your first app', slug: 'getting-started/first-app' },
                { label: 'Configure and build', slug: 'getting-started/configure-and-build' },
                { label: 'Flash, reset and view', slug: 'getting-started/flash-and-view' },
                { label: 'Next steps', slug: 'getting-started/next-steps' },
                { label: 'Migrating from neuralSPOT', slug: 'getting-started/migrate-from-neuralspot' },
              ],
            },
            {
              label: 'Guides',
              href: `${basePath}guides/`,
              sidebar: [{ label: 'Overview', slug: 'guides' }],
            },
            {
              label: 'Modules',
              href: `${basePath}modules/`,
              sidebar: modulesSidebar.items,
            },
            {
              label: 'Reference',
              href: `${basePath}reference/`,
              sidebar: [
                { label: 'Overview', slug: 'reference' },
                { label: 'CLI', collapsed: false, items: referenceSidebar.cli },
                { label: 'Python API', collapsed: true, items: referenceSidebar.api },
                { label: 'Configuration', collapsed: true, items: referenceSidebar.config },
              ],
            },
          ],
          /* llms.txt and the agent-facing bundle are AmbiqAI/neuralspotx#261;
             the rest costs nothing on a site that already has an absolute
             `site` and per-page frontmatter. */
          discoverability: {
            ogImage: true,
            jsonLd: true,
            markdown: true,
            llms: false,
          },
          footer: {
            links: [
              {
                label: `Docs: ${buildInfo.version} · ${buildInfo.shortCommit}${buildInfo.modified ? ' (modified)' : ''}`,
                href: buildInfo.sourceUrl,
              },
              { label: 'Getting started', href: `${basePath}getting-started/` },
              { label: 'Guides', href: `${basePath}guides/` },
              { label: 'Modules', href: `${basePath}modules/` },
              { label: 'Reference', href: `${basePath}reference/` },
              { label: 'GitHub', href: 'https://github.com/AmbiqAI/neuralspotx' },
            ],
            tagline: 'Ambiq Micro, Inc. An AI and embedded development vehicle for Ambiq SoCs.',
            logo: 'ambiq',
          },
        }),
      ],
    }),
  ],
  vite: { plugins: [tailwindcss()] },
});
