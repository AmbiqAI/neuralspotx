# HANDOFF: docs migration cutover (#261 PR 2)

## Goal

Publish the Astro site from `main` and remove the MkDocs and zensical stack it
replaces, so there is one current public site. This is the last PR of the
migration in `tasks/256-docs-migration/plan.md` (parent AmbiqAI/neuralspotx#256).
Branch `261-cutover`, stacked on `261-discoverability`, not pushed.

## What is done, and how far it is verified

Verified locally on macOS (Node 24.12.0):

- `npm run check`, `npm run build` (150 pages), `npm run validate`, the full
  pytest suite, `pre-commit --hook-stage manual`, `ty check` and `actionlint`
  on `docs.yml` all pass.
- `git grep` for mkdocs, zensical, deploy-pages, `docs/stylesheets`,
  `docs/javascripts` and `site/` returns nothing live outside `tasks/` and the
  changelog's history.

Not verified, and not verifiable before the first deployment: everything the
deploy job does. `docs.yml` has never run its deploy path, GitHub Pages has
never served this artifact, and the freshness guard has never had a second run
to stand down against. `tasks/256-docs-migration/p4-notes.md` has the list of
what to check live, in order, the first time it publishes.

Content state: all five sections are written, the Reference and Modules
sections are generated on every build, and all 67 MkDocs routes redirect.
helia-ui is pinned to the released tag `v0.1.0-alpha.15`, not to a commit.
Per-phase detail is in `tasks/256-docs-migration/p1a-notes.md`, `p1b-notes.md`,
`p2-pr1-notes.md`, `p2-pr2-notes.md`, `p3-notes.md` and `p4-notes.md`.

## Before merge

**Visual review.** The plan schedules it at P4 and it has not happened.
Desktop and mobile, light and dark, at least Home, a Guides page, the module
catalog and a Python API page.

**Make "Build and validate" a required check on `main`.** `docs.yml` now runs
unfiltered, on every push and every pull request, so the job always reports a
real result instead of skipping. It is the only place
`tests/test_reference_generation.py` and `tests/test_public_surface_doc.py`
execute, because both read generated output and skip without it, so today a
change that breaks the public surface can merge on a green `ci.yml`. This is a
branch-protection setting, not a repository change, so it is yours to make.

## Decided, so do not reopen these in review

Owner decisions taken 2026-09-20:

- **Windows execution is waived for this pass.**
  `astro-site/src/content/docs/getting-started/install/windows.md` and the
  Windows tab ship unvalidated against a Windows host.
- **Hardware transcripts ship as described output** until someone captures
  them. `nsx probes`, `nsx flash`, `nsx reset` and `nsx view` are described
  rather than captured, and `flash-and-view.mdx` carries a caution saying so.
  Capturing them needs a connected `apollo510_evb`.
- **The onboard J-Link claim stays out** of the install and flash pages.
- **The migration matrix labels stand** as written.
- **The 67-route redirect map is final**, including the seven routes with no
  published successor, which point at the nearest published page.
  `p3-notes.md` section 3 has the table and what would change each one.
- **Release mechanics leave the public site.** The user-facing half is
  `/reference/releases/`; the workflow detail is `docs/maintainers/releases.md`.
- **`helia-dsp` stays unchecked.** It is a private repository, so the docs
  drift check cannot read its manifest without a token. The allowlist marks it
  unchecked and its module page says so, which means its manifest fields are
  not covered by CI. Accepted as it stands rather than granting the docs job a
  read token; nothing else in that job needs credentials. Revisit only if a
  docs read token is granted for another reason.

## Open owner decisions

None outstanding. Everything above is decided; the two items under "Before
merge" are actions, not decisions.

## Product findings from the migration, now tracked

Each of these is a product bug or gap the migration surfaced, not a docs
change, and each has its own issue:

- AmbiqAI/neuralspotx#265: four SDK modules are absent from the registry's
  top-level map, so they have no catalog page. `nsx-timer` (required by
  `nsx-power` and `nsx-usb`), `nsx-interrupt` (required by `nsx-uart`) and
  `nsx-harness` (optional for `nsx-ethos-u-driver`) render as plain names. The
  set is pinned in `tests/test_module_data_snapshot.py`, so a fifth is a
  decision rather than a silent change.
- AmbiqAI/neuralspotx#266: there is no `nsx --version`.
- AmbiqAI/neuralspotx#267: the `STACK_SIZE` comment in `board.cmake` is wrong
  by a factor of four.
- AmbiqAI/neuralspotx#268: `nsx.yml` `source.git` is accepted by the loader and
  rejected by the resolver.
- AmbiqAI/neuralspotx#269: the npu template README states a silicon MAC count
  with no source of record.

## Gotchas

- **The Markdown rendition is derived from the MDX source, not the HTML.**
  Anything that only exists in a component prop is absent from
  `dist/<route>/index.md`. Authored pages are therefore plain `.md`, and the
  example READMEs are inlined at build time.
  `astro-site/scripts/publish-agent-bundle.mjs` repairs the generated routes
  after the build; a new generated section has to be taught to it.
- **A page with no sidebar entry is filed under "Other pages" in `llms.txt`,
  silently.** `check-discoverability-output.mjs` now fails on that for
  everything except Home and the 404.
- **Missing `description` front matter fails the build** and names the paths.
  Generators have to supply one per page.
- **The module snapshot is committed; the pages built from it are not.**
  `astro-site/src/data/{modules,boards}.json` are tracked. Regenerating them
  needs network access to the module repositories and credentials for
  `helia-dsp`.
- **Clones are keyed by `(project, revision)`.** `nsx-npu` pins `v5.2.25` while
  the rest of `nsx-ambiq-sdk` sits on `v5.2.24`.
- **The reference build shells out to `uv run --group docs`** for griffe. A tree
  synced without that group needs `uv sync --group docs` first.
- **`astro.config.mjs` imports generated `src/data/build-info.json`.** Every
  script that loads the config needs the `pre*` hook, `check` included.
- **The lockfile records helia-ui as `git+ssh://`,** which is how npm writes any
  `github:` spec. The repo is public, so npm falls back to HTTPS and no token is
  needed. heliaRT ships the identical entry.
- **Three build warnings are Starlight and Astro internals** with no site-side
  fix: the MDX `use astro:head-inject` note, the empty `i18n` collection, and
  the `/404` route priority note.
- **helia-ui parts are imported through the export map**
  (`@ambiqai/helia-ui/astro/<Part>`). Do not reach into `node_modules` by
  relative path and do not patch it.

## Refs

- Issue AmbiqAI/neuralspotx#261, parent #256. Earlier phases: #257, #258, #259,
  #260.
- Plan: `tasks/256-docs-migration/plan.md`. Cutover notes:
  `tasks/256-docs-migration/p4-notes.md`.
- Upstream gaps filed against helia-ui, per phase:
  `tasks/256-docs-migration/helia-ui-gaps-{258,259,260,261}.md`. Filed:
  AmbiqAI/helia-ui#115 to #121 from the earlier phases and #133 to #143 from
  this one. #124 is merged; #131 was closed as not a bug. The rest are open.
- Reference implementation: `AmbiqAI/helia-rt`, `astro-site/` on `main`.
- Maintainer docs, unpublished: `docs/maintainers/`. Contributor entry point:
  `CONTRIBUTING.md`.

## Visual pass (handed over)

The owner will have a separate session improve the look and feel once this
branch is merged. Content, generation and checks are the contract of this
branch; visual choices are open. Known items for that pass, none of them
blocking: the "Read more:" link rows under each Home card grid (they exist
only for the Markdown rendition until helia-ui#143 ships in alpha.16, then
they go); the hero walkthrough (`astro-site/src/components/JourneyWalkthrough.astro`,
proposed upstream as a helia-ui part in `tasks/256-docs-migration/helia-ui-gaps-260.md`
Draft 8); capability cards on Home (Card + IconTile composition); the plain
hero ground; the catalog toolbar (`ModuleBrowser.tsx`, helia-ui React parts).
Rules that must survive the pass: helia-ui parts only, no local CSS beyond a
justified component rule, every claim on Home traces to a file, and the
rendition and count checks in `astro-site/scripts/check-output.mjs` stay green.
