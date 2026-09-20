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
Per-phase detail is in `tasks/256-docs-migration/p1a-notes.md`, `p1b-notes.md`,
`p2-pr1-notes.md`, `p2-pr2-notes.md`, `p3-notes.md` and `p4-notes.md`.

## Before merge

**Switch the helia-ui pin from a commit to a tag.**
`astro-site/package.json` pins
`github:AmbiqAI/helia-ui#266f614958eae8ace4ada151c9d0bed0677203d1`, the
Markdown-callouts commit (AmbiqAI/helia-ui#128), because it landed after
`v0.1.0-alpha.14` and the site's asides need it. No tag contains it yet.
When the next alpha is cut:

```bash
gh api repos/AmbiqAI/helia-ui/releases --jq '.[0].tag_name'   # confirm it exists
# confirm the tag contains 266f614:
gh api repos/AmbiqAI/helia-ui/compare/<tag>...266f614 --jq .status   # want "identical" or "behind"
cd astro-site
npm pkg set 'dependencies.@ambiqai/helia-ui=github:AmbiqAI/helia-ui#<tag>'
npm install && npm run check && npm run build && npm run validate
```

Commit `package.json` and `package-lock.json` together. Do not merge on the
commit pin: it is not a release, so nothing guarantees it stays reachable.

**Visual review.** The plan schedules it at P4 and it has not happened.
Desktop and mobile, light and dark, at least Home, a Guides page, the module
catalog and a Python API page.

## Needs hardware or another host

- **Four transcripts.** `nsx probes`, `nsx flash`, `nsx reset` and `nsx view`
  are described rather than captured, and
  `astro-site/src/content/docs/getting-started/flash-and-view.mdx` carries a
  caution saying so. Replacing them needs a session on a connected
  `apollo510_evb`.
- **Windows install steps.** Never executed on a Windows host.
  `astro-site/src/content/docs/getting-started/install/windows.md` and the
  Windows tab of the install page are unvalidated.
- **`helia-dsp` manifest fields.** The module is private, so a CI job with no
  credentials reports it as not checked rather than as drift. Its manifest
  prose is not covered by the snapshot check.

## Open owner decisions

1. **Seven old routes have no published successor** and point at the nearest
   published page. The table of what each points at and what would change it is
   in `p3-notes.md` section 3. Two moved in this PR: `/contributing/releases/`
   now lands on the new `/reference/releases/`, and
   `/contributing/docs-workflow/` lands on `/guides/` because the rewritten
   docs-workflow is maintainer material and the Contribute group has no index
   page. Writing a Contribute overview page would settle three of the seven.
2. **`/user-guide/module-catalog/` was dropped**, the single largest old page,
   in favor of the generated catalog. Its twenty anchors are unrecoverable;
   `p3-notes.md` lists what answers each question now.
3. **Four declared dependencies name modules the registry does not pin:**
   `nsx-timer` (required by `nsx-power` and `nsx-usb`), `nsx-interrupt`
   (required by `nsx-uart`) and `nsx-harness` (optional for
   `nsx-ethos-u-driver`). The catalog renders an unknown dependency as a plain
   name. The set is pinned in `tests/test_module_data_snapshot.py`, so a fifth
   is a decision rather than a silent change.
4. **The Python API page is at 82% of its HTML budget and 84% of its gzip
   budget**, warning by design so it gets split before it fails. Splitting it
   is not in this PR.

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
  `tasks/256-docs-migration/helia-ui-gaps-{258,259,260,261}.md`. All are open
  against `v0.1.0-alpha.14`.
- Reference implementation: `AmbiqAI/helia-rt`, `astro-site/` on `main`.
- Maintainer docs, unpublished: `docs/maintainers/`. Contributor entry point:
  `CONTRIBUTING.md`.
