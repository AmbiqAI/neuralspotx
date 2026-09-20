# neuralSPOT-X docs: migration to Astro + helia-ui (plan for AmbiqAI/neuralspotx#256)

Status: APPROVED direction (owner decisions 2026-09-20 recorded in section 7). Sub-issues being drafted.

## 1. Audit findings (Done)

Stack today
- Renderer: mkdocs-material config in `mkdocs.yml`, built with zensical (pyproject `docs` group: mkdocs-material, pymdown-extensions, zensical 0.0.29 in uv.lock). Plugins: search only. No API generation, no redirects plugin, no llms.txt, sitemap, robots or CNAME.
- Publish: `.github/workflows/deploy-pages.yml` on push to main and manual dispatch, builds `./site`, deploys with actions/deploy-pages. Release workflow does not publish docs, so there is no release-vs-main ordering hazard today. Live site: https://ambiqai.github.io/neuralspotx/ (HTTP 200, no sitemap).
- Custom UI: landing page with bespoke `.l-*` CSS in `docs/stylesheets/extra.css`; SimpleDatatables JS for the catalog table; one asset `docs/assets/neuralspotx-icon.png`. Colors teal, fonts Inter + JetBrains Mono.

Content: 67 pages, ~6,200 lines, in 7 nav groups
- Getting Started 6 pages (install index + macOS/Linux/Windows, first app).
- User Guide 15 pages. Largest and most valuable: custom-modules (456 lines), module-catalog (289), startup-and-linker (256), lock-and-sync (222), system-init (172), memory-placement (163), modules (166), python-api (141).
- Command Reference 13 pages: hand-written pages for 11 commands plus CLI overview and Public Python API. The CLI actually has 20 top-level commands (argparse, entry `neuralspotx.cli:main`). No pages for `lock`, `sync`, `outdated`, `update`, `probes`, `board`, `cache`.
- Architecture 11 pages: mix of user-relevant concepts (app generation flow, dependency, module, metadata, SDK provider, multi-target models, toolchain support) and maintainer/planning material (design decisions, sdk-upstream-plan, board coverage).
- Examples 11 pages: index plus 10 stubs that include each example's README via snippet with front matter (tier, capabilities, status, boards_tested).
- Contributing 10 pages: index, agent guidance, repo layout, docs workflow, releases (220 lines), adding boards/modules, internal module coverage, migration from neuralSPOT (203 lines). `contributing/sdk-providers.md` is an orphan not in the nav.

Public surfaces and sources of truth
- Python API: `neuralspotx.__all__` exports 80 names (10 errors, 3 emitter types, ~40 callables, 20+ models). `docs/reference/public-api.md` is a manual inventory kept in sync by `tests/test_public_surface_doc.py`; everything is marked Provisional.
- CLI: argparse tree in `src/neuralspotx/cli/__init__.py`; many subcommands already support `--json`.
- Module catalog: registry lock `src/neuralspotx/data/registry.lock.yaml` pins 50 modules as {project, revision, metadata path}. Each module ships `nsx-module.yaml` (required: name, type, version, support, build, depends, compatibility.{boards,socs,toolchains}; optional: summary, capabilities, use_cases, anti_use_cases, agent_keywords, example_refs, composition_hints, provides, constraints, integrations). Module types: sdk_provider, soc, board, runtime, portable_api, algorithm, tooling, backend_specific. `nsx module list --registry-only --json` and `nsx module describe --json` expose this.
- Drift already exists: the hand-written catalog page names 52 modules over 98 table rows against 50 in the registry lock. No script maintains it.
- Boards: 17 `src/neuralspotx/boards/<board>/board.yaml` (tier is evb for 16, fpga for 1; soc, sdk_provider, cpu, toolchains) plus ordering in `constants.py`. SoC families in the registry lock. Toolchains have no central list (gcc, armclang, atfe appear in board and module compat).
- Validation evidence: registry policy and metadata are unit tested in CI. There is no per-board hardware validation matrix for modules. The catalog must say "declared compatible", never "validated".

Shared foundation
- helia-ui v0.1.0-alpha.14 (2026-09-19, weekly alpha cadence), private package installed by git tag. Peer deps astro ^7.0.2, @astrojs/starlight ^0.41.5, React 19, Tailwind 4. Provides `heliaStarlight` plugin (sections, header, footer, accent, discoverability: ogImage, jsonLd, markdown, llms), tokens/semantic/recipes/starlight stylesheets, 45+ Astro parts (Hero, Card*, LinkCard, DataTable, CodeTabs, Callout, Badge, Chip, Timeline, Ref* reference parts) and 30+ React components (data-table, combobox, command, tabs).
- Python reference tooling exists: `helia-ui-pyref` reads a griffe 1.7.3 JSON dump, writes MDX per module, a reference model JSON, llms text bundle, and a sidebar fragment; has `--check` drift mode and a unit test. Developed against helia_aot. NSX would be an early consumer, so expect fixes upstream.
- heliaRT (PR #298, alpha.14) and heliaCORE (PR #522, alpha.13) are merged references: four sections, no Home sidebar, Doxygen-based reference, build/validate/deploy split in `docs.yml`, redirects, provenance footer, per-page size budgets, output checks. RT's lesson: MDX stripping lost component-prop content; publish model-derived Markdown and test completeness.
- Handbook issue #54 boundary: one shared shell and shared vocabulary for common parts; product-specific components stay local on package tokens; gaps go upstream as focused issues/PRs.

## 2. Target information architecture

Top navigation (neutral, five entries; the fifth is the product-specific adjustment the issue invited):
Home | Getting started | Guides | Modules | Reference

Home (no sidebar)
- Keep NSX identity: existing tagline and terminal demo, three-step "install, create, flash" strip, cards into the four sections, "for agents" callout linking llms.txt and the Markdown renditions, latest version + docs commit in footer.

Getting started (task journey, validated against the current CLI)
1. Overview and requirements  2. Install (macOS, Linux, Windows tabs on one page, plus per-OS pages kept for deep links)  3. Run `nsx doctor`  4. Create your first app  5. Configure and build  6. Flash, reset and view output  7. Next steps  8. Migrating from neuralSPOT (moved here from Contributing).

Guides (sidebar groups)
- Apps: app model, app layout, create an app, build/flash/view, boards and targets, troubleshooting.
- Modules in your app: using modules, custom modules, lock and sync, version pinning, SDK provider selection, source vs prebuilt integration (only where code supports it).
- System: system initialization, memory placement, startup and linker, toolchain support.
- Concepts (from Architecture, rewritten for users): app generation flow, dependency model, module model, metadata model, multi-target and portability, SDK provider model.
- Python API guide (how to drive NSX from Python and from agents).
- Examples: overview with the tier/capability/board front matter rendered as a filterable table, one page per example (README included as today).
- Contribute (collapsed, at the bottom): agent guidance, adding a board, adding a module, docs workflow.

Modules (new section; the highlight the owner asked for)
- Catalog page: generated, filterable by type, SoC, board, toolchain, capability; columns name, type, summary, version, SoCs, boards (declared), repo. Client-side filtering over a small JSON; full table also rendered statically so Pagefind, Markdown rendition and agents see it.
- One generated page per module (recommend doing it in this migration, not later; the data is already in the manifests): summary, capabilities, use cases and anti-use-cases, provides, depends (required/optional), compatibility, constraints, example refs, project + revision, `nsx module add` snippet. This is the stable URL agents will cite. Deeper per-module API docs stay in module repos for a later phase.
- Board matrix: generated from board.yaml (board, SoC, tier, SDK provider, toolchains).
- "How compatibility is declared" note: manifest-declared, not hardware-validated.

Reference
- CLI: overview plus one generated page per command and subcommand (all 20, options tables from the argparse tree, existing hand-written notes merged in as prose blocks).
- Python API: generated from `neuralspotx.__all__` via griffe + helia-ui-pyref; grouped errors / models / functions / emitters; Provisional status shown once per page, not per symbol.
- Configuration: `nsx-app.yaml`, `nsx-module.yaml`, `board.yaml`, registry lock schema; field tables derived from the validators in `metadata.py` (generated where practical, otherwise a manifest that a test compares to the loader).
- Releases and versioning policy (user-facing part of contributing/releases).

Out of the public site (repo Markdown, not published)
- design-decisions, sdk-upstream-plan, board-coverage, internal module coverage, release mechanics, repo layout, docs workflow. Consolidate into a root `CONTRIBUTING.md` (short) with the long pieces as plain Markdown under `docs/maintainers/`, excluded from the site build. Owner direction: the site is for customers and users only.

## 3. Generation and agent-facing delivery

- Module data: `scripts/docs/build_module_data.py` uses the public API (`list_modules`, `describe_module`) to write `astro-site/src/data/modules.json` and `boards.json`. Commit the snapshot; a CI check regenerates and fails on drift, so the Astro build itself is offline and reproducible (manifests live in other repos, fetched by nsx).
- CLI data: `scripts/docs/dump_cli.py` walks the argparse tree to JSON (commands, subcommands, options, defaults, help). An Astro component renders pages; llms bundle gets the Markdown form. Test: every registered command appears.
- Python API: `griffe dump neuralspotx --docstyle google` then `helia-ui-pyref` with `--public`, `--commit`, `--source-url`. Test: every `__all__` name has an anchor; nothing outside `__all__` is exposed except types they reference. Replace `test_public_surface_doc.py` with a check against the generated model.
- Discoverability: helia-ui plugin markdown + llms options, Pagefind, sitemap, canonical URLs, JSON-LD. Publish `/llms.txt`, `/llms-full.txt` (prose + API + CLI + catalog + per-module pages), `/modules/catalog.json`, and `.md` renditions for every route. Completeness tests read the bundle and assert symbol, command and module names, not file existence.
- Provenance: footer shows package version and docs commit (as RT).
- Budgets: record extraction and build times; per-page HTML and gzip budgets as RT; split API pages by group.

## 4. Delivery and cutover

- New `.github/workflows/docs.yml`: PR job builds and validates the artifact (Astro strict check, link/anchor check, redirects, reference completeness, catalog drift, size budgets) with no credentials; main job reuses the validated artifact and deploys with a freshness guard. Docs-only changes publish from main without a release. Release workflow untouched (it does not publish docs).
- Redirects: authored map for all 67 current routes to new routes; a real 404 with Home and Reference links; no blanket API-anchor fallback to Home.
- Cutover PR removes `mkdocs.yml`, `docs/stylesheets`, `docs/javascripts`, zensical and mkdocs deps (after checking no other workflow uses them), `deploy-pages.yml`; updates AGENTS.md, CONTRIBUTING and contributing/docs-workflow for the new authoring flow (Markdown for prose, MDX for composed pages, islands only for the catalog filter).

## 5. helia-ui interaction

- Pin v0.1.0-alpha.14, lockfile committed, clean Linux install verified in CI; bump deliberately.
- Expected upstream items (file as focused issues/PRs on AmbiqAI/helia-ui as they are hit): pyref hardening against dataclasses, Protocols, Literal and Optional annotations, re-exports through `__all__`; a maturity/status Badge vocabulary if the package lacks one (handbook #54 keeps StatusBadge local, so first check whether a shared variant is wanted); DataTable faceted filtering if the Astro DataTable is static-only; already open: ChipRow #79, reference grouping config #71, footer copyright #67.
- Terminal and code rendering: helia-ui already ships `AsciiTerminal` (typed transcript with line kinds command/output/success/warning/error, autoplay on scroll, copy and replay, reduced-motion aware), `CodeBlock`, `CodeTabs` and `Reveal`. Use `AsciiTerminal` for the Home demo and for every "what you should see" step in Getting started (doctor, create, build, flash, view). Extension candidates to propose upstream once a concrete page needs them: timed reveal of output lines (today only command lines animate), ANSI colour spans inside output, a multi-scene transcript (one frame, several steps), and OS tabs around a transcript (CodeTabs + AsciiTerminal composition).
- NSX-local components: ModuleCatalog (filter island), ModuleCard, BoardMatrix, CliCommand renderer.

## 6. Phases and sub-issues (each a PR through adversarial review, light review, CI)

P0 Scaffold (1 PR): `astro-site/` with helia-ui pin, shell config, five sections, Home draft, `docs.yml` build+validate only, pyref smoke run on `neuralspotx`. Gate: clean Linux build in CI.
P1 Generators (2 PRs, parallel worktrees): (a) Python API + CLI + config reference with completeness checks; (b) module/board data snapshot, catalog, per-module pages, drift check.
P2 Content (3 PRs by section, can run parallel to P1b): Getting started rewritten and command-validated; Guides reorganized and Concepts rewritten; Modules and Examples sections.
P3 Discoverability and routes (1 PR): llms, Markdown renditions, sitemap, JSON-LD, redirects map, 404, provenance, budgets, completeness tests.
P4 Cutover (1 PR): deploy from main, remove old stack, update maintainer docs, verify live commit, search, redirects, 404, catalog JSON, llms content.
P5 Later, separate issue: per-module API docs inside module repos with a shared template in `templates/nsx-module-ci`.

Rough sizing: P0 and P3 small; P1a, P1b medium; P2 large (content quality is the real work); P4 small. Visual review (desktop/mobile, light/dark) happens at P2 and P4.

## 7. Owner decisions (2026-09-20)

1. Modules is its own top-level section.
2. Generate a page per module in this migration.
3. Maintainer material leaves the site: root CONTRIBUTING.md plus unpublished Markdown under docs/maintainers/.
4. Module and board data is a committed snapshot with a CI drift check.
5. Use helia-ui's AsciiTerminal (and CodeBlock/CodeTabs/Reveal) for terminal and code rendering across Home and Getting started; extend upstream where a page needs more.
6. Product name stays neuralSPOT-X with NSX as the CLI name.

## 8. Risks

- helia-ui alpha churn (weekly): pin and bump on purpose; budget one upstream PR round per phase.
- pyref smoke test on the real package (2026-09-20, helia-ui origin/main, griffe 1.7.3): griffe dump 0.6 s, pyref 0.1 s, 79 MDX pages, llms-full.txt 256 KB, all 80 `__all__` names rendered, dataclass fields, defaults and union signatures render correctly. Two gaps to take upstream first: (1) no public-surface filter, so 59 private `_module` pages are emitted; (2) 106 unresolved cross-references for types re-exported through the package root (AppCreateRequest, CacheEntry and similar), because links target the public path while pages live at the private module path. pyref already has a repeatable `--filter <pattern>` (exclude with `!`) and an `__all__` re-export list per module, and griffe dump has `-r/--resolve-aliases`; P1a must first try `--filter '!^_'` plus alias resolution before any NSX-side workaround. Interim NSX-side fallback: pre-filter the griffe JSON to `__all__` plus referenced types and rewrite paths to the public names before rendering.
- Module manifests live in other repos: snapshot approach keeps the build hermetic but needs the drift check to stay honest.
- All 80 public symbols are Provisional; docs must say so without burying the reference.
- Install pages, especially Windows, need command validation against the current CLI, which is a runner task, not a docs task.
