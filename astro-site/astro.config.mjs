// SPDX-License-Identifier: BSD-3-Clause
// Copyright (c) 2026, Ambiq
// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import react from '@astrojs/react';
import tailwindcss from '@tailwindcss/vite';
import { heliaStarlight } from '@ambiqai/helia-ui/starlight';
// Written by scripts/build-reference.mjs, which every dev, check and build run
// invokes through prepare:docs before Astro starts.
import referenceSidebar from './src/data/reference-sidebar.json' with { type: 'json' };
// Written by scripts/build-modules.mjs from the committed module snapshot, in
// the same prepare:docs pass (AmbiqAI/neuralspotx#259).
import modulesSidebar from './src/data/modules-sidebar.json' with { type: 'json' };
// Written by scripts/build-examples.mjs from each example README's front matter
// and body, in the same pass (AmbiqAI/neuralspotx#260).
import examplesSidebar from './src/data/examples-sidebar.json' with { type: 'json' };
// Every route the MkDocs site published, mapped to its successor
// (AmbiqAI/neuralspotx#261). Authored from the fate table in
// tasks/256-docs-migration/p2-content-map.md; checked against dist by
// scripts/check-discoverability-output.mjs.
import oldRoutes from './src/data/redirects.json' with { type: 'json' };

const base = '/neuralspotx';
const basePath = `${base}/`;

/* An old route that kept its path is a page, not a redirect, and Astro would
   refuse a redirect that collides with one. Those entries stay in the map
   because the check reads it as the list of routes that must still resolve,
   not as the list of stubs to emit. */
const redirects = Object.fromEntries(
  Object.entries(oldRoutes).filter(([from, to]) => to !== `${base}${from}`),
);

export default defineConfig({
  site: 'https://ambiqai.github.io',
  base,
  redirects,
  integrations: [
    /* The module catalog's filter is the site's one island
       (src/components/ModuleCatalogFilter.tsx). */
    react(),
    starlight({
      title: 'neuralSPOT-X',
      description:
        'The modular AI SDK for Ambiq silicon: compose firmware modules, choose a toolchain and build for Ambiq silicon.',
      favicon: '/neuralspotx-icon.png',

      /* site-theme.css last, so its dials land on top of the package sheets
         the plugin splices in ahead of it. */
      customCss: ['./src/styles/tailwind.css', './src/styles/site-theme.css'],
      plugins: [
        heliaStarlight({
          header: {
            title: 'neuralSPOT-X',
            hub: {
              label: 'HELIA HUB',
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
              label: 'User guide',
              href: `${basePath}guides/`,
              /* Task groups are open because they are what a reader came for;
                 Concepts, Examples and Contribute are collapsed so the four
                 task groups stay visible without scrolling. */
              sidebar: [
                { label: 'Overview', slug: 'guides' },
                {
                  label: 'Build and run',
                  collapsed: false,
                  items: [
                    { label: 'The app model', slug: 'guides/apps/app-model' },
                    { label: 'App layout', slug: 'guides/apps/app-layout' },
                    { label: 'Build, flash and view', slug: 'guides/apps/build-flash-view' },
                    { label: 'Troubleshooting', slug: 'guides/apps/troubleshooting' },
                  ],
                },
                {
                  label: 'Manage modules',
                  collapsed: false,
                  items: [
                    { label: 'Using modules', slug: 'guides/modules/using-modules' },
                    { label: 'Lock and sync', slug: 'guides/modules/lock-and-sync' },
                    { label: 'Custom modules', slug: 'guides/modules/custom-modules' },
                  ],
                },
                {
                  label: 'Hardware and toolchains',
                  collapsed: false,
                  items: [
                    { label: 'Boards and targets', slug: 'guides/apps/boards-and-targets' },
                    { label: 'Board matrix', slug: 'modules/boards' },
                    { label: 'Toolchains', slug: 'guides/system/toolchains' },
                    { label: 'SDK foundation and overrides', slug: 'guides/modules/sdk-providers' },
                  ],
                },
                {
                  label: 'Firmware',
                  collapsed: false,
                  items: [
                    { label: 'System initialization', slug: 'guides/system/system-init' },
                    { label: 'Memory placement', slug: 'guides/system/memory-placement' },
                    { label: 'Startup and linker', slug: 'guides/system/startup-and-linker' },
                  ],
                },
                { label: 'Examples', collapsed: true, items: examplesSidebar.items },
                {
                  label: 'Automation', collapsed: true,
                  items: [
                    { label: 'Python API guide', slug: 'guides/python-api' },
                    { label: 'Automation and agents', slug: 'guides/contribute/agent-guidance' },
                  ],
                },
                {
                  label: 'Architecture',
                  collapsed: true,
                  items: [
                    { label: 'Overview', slug: 'guides/concepts' },
                    { label: 'App generation flow', slug: 'guides/concepts/app-generation-flow' },
                    { label: 'Dependency model', slug: 'guides/concepts/dependency-model' },
                    { label: 'Module model', slug: 'guides/concepts/module-model' },
                    { label: 'Metadata model', slug: 'guides/concepts/metadata-model' },
                    { label: 'Multi-target and portability', slug: 'guides/concepts/multi-target' },
                  ],
                },
                {
                  label: 'Extend NSX',
                  collapsed: true,
                  items: [
                    { label: 'Add a board', slug: 'guides/contribute/adding-a-board' },
                    { label: 'Contribute a module', slug: 'guides/contribute/adding-a-module' },
                  ],
                },
              ],
            },
            {
              label: 'Modules',
              href: `${basePath}modules/`,
              sidebar: modulesSidebar.items,
            },
            {
              label: 'API reference',
              href: `${basePath}reference/`,
              sidebar: [
                { label: 'Overview', slug: 'reference' },
                { label: 'CLI', collapsed: false, items: referenceSidebar.cli },
                { label: 'Python API', collapsed: true, items: referenceSidebar.api },
                { label: 'Configuration', collapsed: true, items: referenceSidebar.config },
                /* Hand-written, unlike everything above it, because release
                   policy has no model to generate from. It is the successor
                   the /contributing/releases/ redirect lands on (#261). */
                { label: 'Releases and versioning', slug: 'reference/releases' },
              ],
            },
          ],
          /* The plugin reads authored source, so its llms.txt, llms-full.txt
             and per-route renditions miss everything the generated pages hold
             in component props. scripts/publish-agent-bundle.mjs rewrites both
             from the reference and module models after the build. */
          discoverability: {
            ogImage: true,
            jsonLd: true,
            markdown: true,
            llms: true,
          },
          footer: {
            links: [
              { label: 'Getting started', href: `${basePath}getting-started/` },
              { label: 'User guide', href: `${basePath}guides/` },
              { label: 'Modules', href: `${basePath}modules/` },
              { label: 'API reference', href: `${basePath}reference/` },
              { label: 'GitHub', href: 'https://github.com/AmbiqAI/neuralspotx' },
            ],
            tagline: 'Part of the Ambiq HELIA AI platform',
            logo: 'ambiq',
          },
        }),
      ],
    }),
  ],
  vite: { plugins: [tailwindcss()] },
});
