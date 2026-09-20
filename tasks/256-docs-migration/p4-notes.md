# P4 notes: cutover and removal (AmbiqAI/neuralspotx#261, PR 2)

Branch `261-cutover`, stacked on `261-discoverability`, not pushed. Scope is the
second half of #261: deploy the validated artifact from `main`, remove the
MkDocs and zensical stack, give the maintainer material and the example front
matter a home outside `docs/`, and write the one Reference page the redirect map
was pointing at a section index for.

## 1. The deploy job

`.github/workflows/docs.yml` gains a `deploy` job. The build job is unchanged
except for one new step and one new output.

| Property | Value, and why |
| --- | --- |
| Gate | `github.repository == 'AmbiqAI/neuralspotx' && github.ref == 'refs/heads/main' && (push or workflow_dispatch)`. A fork cannot deploy, a pull request cannot deploy, and a dispatch from a branch other than `main` cannot deploy. |
| Artifact | `actions/download-artifact` of `neuralspotx-docs-site`, the same artifact the build job uploaded after `validate` passed. Nothing is rebuilt, so what goes live is byte for byte what the checks ran against. |
| Permissions | `pages: write` and `id-token: write` on the deploy job only. The workflow level stays `contents: read`, which is what a pull request run gets, so PR validation needs no credentials and no environment. |
| Concurrency | `group: github-pages`, `cancel-in-progress: false`, on the job rather than the workflow. Pages allows one deployment at a time and a cancelled deploy leaves the site on whatever was published last, so these queue. The workflow-level `docs-site-<ref>` group is unchanged and still cancels pull request runs. |
| Environment | `github-pages`, with `url` from the deploy step, so the deployment shows on the commit and in the environment history. |

Action versions are pinned by SHA with a version comment, matching the build
job's existing pins: `download-artifact` v4, `configure-pages` v5,
`upload-pages-artifact` v3, `deploy-pages` v4. Each SHA was resolved from the
tag through the GitHub API rather than written from memory.

### The freshness guard

The build job records `git rev-parse HEAD` into a `source_commit` output. The
deploy job's first step reads the tip of `main` through `gh api` and compares:

```
latest=$(gh api "repos/$GH_REPO/branches/main" --jq .commit.sha)
[[ "$latest" == "$DOCS_SOURCE_COMMIT" ]]
```

If they differ, a newer commit owns the public site, and every remaining step is
skipped through `if: steps.freshness.outputs.publish == 'true'`. The job still
succeeds, so a stood-down run is not a red check; it just publishes nothing.
This is heliaRT's pattern.

The commit is recorded in the build job rather than read again in the deploy
job on purpose. Reading it twice would compare the tip of `main` against
whatever the deploy job happened to check out, which is not the commit the
artifact was built from. The workflow-level concurrency group already serializes
two `main` pushes, so the guard is the second line of defense rather than the
first; it is what covers a `workflow_dispatch` run racing a push, and a queued
run whose turn comes after the branch has moved.

### Release publishing

`.github/workflows/release.yml` contains no reference to docs, Pages,
`deploy-pages` or `docs.yml`, verified by grep over `.github/`. It did not
publish documentation before this PR and it does not now. Docs-only changes
reach the site from `main` with no release, which is the point of deploying
from `docs.yml` rather than from the release path.

### No path filters

The `paths:` lists are gone from both the push and the pull request triggers, so
`docs.yml` runs on every push to `main` and every pull request. Adversarial
review found the reason, and it is a real failure rather than a preference: the
freshness guard publishes only when the commit it built is still the tip of
`main`, so with a filtered trigger a docs commit followed by a non-docs commit
strands the site. The docs run holds a commit that is no longer the tip and
stands down, and the non-docs commit never starts a run to take over. The site
would stop updating with nothing failing.

A second reason stands on its own. This workflow is the only place
`tests/test_reference_generation.py` and `tests/test_public_surface_doc.py`
execute, because both need the generated reference and skip without it. A
filtered job skips rather than passes, so it cannot serve as a required check.
With the filters gone, "Build and validate" is eligible to be one, which is the
recommendation in `HANDOFF.md`.

The cost is about a minute of CI on every pull request. The alternative
considered and rejected was keeping the filters and having the deploy job
compare against the newest *docs-relevant* commit rather than the tip of
`main`, which means reimplementing GitHub's path matching in shell against the
same filter list, in two places that can disagree.

## 2. What was removed, with the grep proof

Removed:

- `.github/workflows/deploy-pages.yml`
- `mkdocs.yml`
- `docs/stylesheets/` (`extra.css`, `simple-datatables.css`, `table-overrides.css`)
- `docs/javascripts/module-catalog-tables.js`
- `docs/assets/neuralspotx-icon.png`
- `scripts/gen_examples_table.py`
- the `mkdocs-material`, `pymdown-extensions` and `zensical` entries in the
  pyproject `docs` group, and the 25 packages and 411 lines they pulled into
  `uv.lock`
- 58 files under `docs/` that the new site replaced: the whole of
  `getting-started/`, `user-guide/`, `reference/`, `examples/`, plus the
  published parts of `architecture/` and `contributing/`

Kept: `griffe==1.7.3` in the `docs` group. `build-reference.mjs` shells out to
`uv run --group docs griffe`, so the group is still a real group.

The icon needed no move. `astro-site/public/neuralspotx-icon.png` is byte
identical to `docs/assets/neuralspotx-icon.png` (`cmp` clean), so the site
already had it.

Grep before the dependency removal turned up exactly three live references
beyond the files being deleted:

| Reference | Resolution |
| --- | --- |
| `.pre-commit-config.yaml`, `check-yaml` with `args: [--unsafe]` | The flag existed for `mkdocs.yml`'s Python-specific YAML tags. Flag and comment both removed, so YAML is checked strictly again. |
| `README.md`, the Pages badge and the two `zensical` commands | Rewritten for the Astro site. |
| `AGENTS.md`, `uv run --group docs zensical build` in Validation Expectations | Replaced by the three npm commands. |

Plus two comments that named deleted files: `astro-site/src/styles/site-theme.css`
cited `docs/stylesheets/extra.css` as the source of the accent value, and
`src/neuralspotx/__init__.py` pointed at `docs/reference/public-api.md`. Both
were rewritten rather than deleted, because both said something the code could
not. `.gitignore` also carried `/site/`, zensical's output directory, now dead.

After the removal, `git grep -n "mkdocs\|zensical\|deploy-pages\|docs/stylesheets\|docs/javascripts\|site/" -- ':!tasks' ':!HANDOFF.md'`
returns only:

- `astro-site/**` path matches, which the `site/` alternative catches
- `actions/deploy-pages@<sha>`, the action the new deploy job uses
- `CHANGELOG.md` line 686, a released changelog entry, which is history
- `astro-site/package-lock.json` line 57, a bin name inside helia-ui

## 3. What moved where

### Maintainer material, to `docs/maintainers/`

Seven files, plain repository Markdown, no route (plan section 7, owner
decision 3; `p2-content-map.md` section 4):

| File | From | Change beyond the move |
| --- | --- | --- |
| `design-decisions.md` | `docs/architecture/` | none |
| `sdk-upstream-plan.md` | `docs/architecture/` | the `!!! info` admonition became a blockquote, and two relative `.md` links became absolute site URLs |
| `board-coverage.md` | `docs/architecture/` | none |
| `repo-layout.md` | `docs/contributing/` | the owned-paths list now names `astro-site/` and `docs/maintainers/` instead of `docs/` and `mkdocs.yml` |
| `module-coverage.md` | `docs/contributing/` | one relative `.md` link became an absolute site URL |
| `releases.md` | `docs/contributing/` | retitled "Release mechanics", with a pointer to the published user-facing half |
| `docs-workflow.md` | `docs/contributing/` | rewritten from scratch; the MkDocs instructions described nothing that still exists |

`docs-workflow.md` now covers how to run and build the site, what `validate`
asserts, where each generator lives and what it reads, how to add a page, the
two front matter and sidebar rules the build enforces, the rendition rule and
why authored pages are plain `.md`, and the four transcripts that need hardware.

### Root `CONTRIBUTING.md`

New, one page: file an issue first, uv setup, the three checks CI runs, the
pre-commit stage table, how to run the docs site, commit and pull request
conventions including release-please, and an index of both the published
Contribute guides and `docs/maintainers/`. The stage table came from
`docs/contributing/index.md`, which is deleted; it was the only copy and it is
not published anywhere on the site.

### Example front matter, to the READMEs

`docs/examples/<name>.md` was a stub carrying nothing but front matter and a
MkDocs snippet include of the README. The front matter is now on
`examples/<name>/README.md` itself, so the declared tier, status, capabilities
and tested boards sit beside the code they describe.

`build-examples.mjs` now enumerates `examples/*/` by the presence of `nsx.yml`
and reads front matter and body from the one file. The rendered table is
identical: ten rows, same columns, same values.

`scripts/gen_examples_table.py` spliced a second, differently shaped matrix into
`docs/examples/index.md`, which the generated Examples overview replaces, so it
is deleted. Its one check that reached outside the front matter survives:
`tests/test_examples_gallery_drift.py` becomes
`tests/test_examples_front_matter.py`, which asserts required fields, the tier
and status vocabularies, and that every board in `boards_tested` is a target the
app's own `nsx.yml` declares. `build-examples.mjs` cannot make that last
assertion, because it never reads `nsx.yml`.

### The public surface test

`docs/reference/public-api.md` was a hand-maintained table of
`neuralspotx.__all__` kept honest by `tests/test_public_surface_doc.py`. The
page is gone; the test is not. It now pins
`astro-site/public/reference/python-symbols.json`, the catalog the site
publishes, to `__all__` in both directions, and adds a check that each entry's
`path` really is `<module>.<name>` under the package.

That closes a real gap rather than restating an existing test.
`check-discoverability-output.mjs` already asserted the llms bundle covers every
name in `python-symbols.json`, with a comment saying the catalog was pinned to
`__all__` by a Python test, but no test pinned that file: the nearest one pins
`src/data/reference-report.json`, a different artifact. The comment now names
the test that makes it true.

## 4. The Releases and versioning page

`astro-site/src/content/docs/reference/releases.md`, wired into the Reference
sidebar after Configuration and linked from the Reference overview. It is the
user-facing half of the old `contributing/releases.md`: cadence, the
`neuralspotx-v<version>` tag form and its immutability, what Provisional means
against Stable, that nothing is Stable yet, how to pin exactly and why `~=` is
not enough pre-1.0, that modules pin through `nsx.lock` and the SDK through the
provider module, and how to read the installed version.

One claim was cut during drafting: the page first said `nsx doctor` reports the
version. It does not. `nsx doctor` prints tool paths only, and `nsx --version`
does not exist either, which is AmbiqAI/neuralspotx#266, so the page says to ask
the package through `importlib.metadata`. When #266 lands the page should say
`nsx --version` instead.

## 5. Redirect changes

Two entries in `astro-site/src/data/redirects.json` moved off the "no published
successor" list in `p3-notes.md` section 3, or moved within it:

| Route | Was | Now | Why |
| --- | --- | --- | --- |
| `/contributing/releases/` | `/reference/` | `/reference/releases/` | The successor the fate table specified now exists. Settled, not a placeholder. |
| `/contributing/docs-workflow/` | `/guides/contribute/agent-guidance/` | `/guides/` | Open question 4 in `p2-content-map.md` section 6 is answered the other way: docs-workflow is maintainer material and is not published. The Contribute group has no index page, so `/guides/` is the nearest published landing point. |

`/guides/contribute/` is not a route. If a Contribute overview page is ever
written, three entries could be repointed at it: `/contributing/`,
`/contributing/docs-workflow/` and `/contributing/repo-layout/`. That is future
work, not a blocker: the owner has signed the 67-route map off as final.

Count is unchanged: 67 entries, 7 identity, 60 stubs.

## 6. Two checks added this phase

1. **No route under "Other pages" in `llms.txt`.** helia-ui files any page it
   cannot give a sidebar trail into that bucket. It is silent: the page is still
   listed, still counted and still has a rendition, so nothing in a build log
   says an agent reading by section will never arrive at it. Seven routes were
   in there. Home and the 404 belong there, being deliberately outside the
   sidebar, and are allowlisted. The other five were the generated Python API
   module pages, which hold the whole API and had no trail because the API
   sidebar links to anchors. `build-reference.mjs` now emits a "By module" group
   for them, and `check-discoverability-output.mjs` fails on anything else in
   the bucket.
2. **Every page has a `description`.** The plugin already fails the build and
   names the paths, so this needed no new check, only proof: an audit of all 150
   emitted pages found zero missing. The rule is written down in
   `docs/maintainers/docs-workflow.md` so a new generator does not learn it from
   a build failure.

## 7. Measurements

Local, macOS, Node 24.12.0, after the cutover.

| Measure | Before | After |
| --- | --- | --- |
| Routes | 149 | 150 |
| HTML files in dist | 209 | 210 |
| Files under `docs/` | 72 | 7 |
| Packages in `uv.lock` | 47 | 22 |
| Workflows | 4 | 3 |
| Entries under llms.txt "Other pages" | 7 | 2 |
| Python API page, HTML budget | 81% | 82% |

The Python API page moved because the new sidebar group adds markup to every
page. It is still under the 80% warning threshold's failure point and still
warning, by design, so it gets split before it fails.

## 8. Verification: what can only be checked live

Everything below needs the first deployment, because the deploy job has never
run, Pages has never served this artifact, and no second run has ever had to
stand down. None of it is verified.

After the first publish from `main`:

1. **The workflow.** The deploy job ran, the `github-pages` environment shows
   the deployment, and the build job was not run twice.
2. **Source commit.** The footer on any page names the merge commit and the
   package version, and `https://ambiqai.github.io/neuralspotx/build-info.json`
   reports the same 40-character hash.
3. **Search.** Pagefind returns hits for a public symbol (`create_app`), a CLI
   command (`nsx module add`) and a module name (`nsx-helia-rt`).
4. **Redirects.** Spot-check one of each kind against the live origin:
   `/neuralspotx/user-guide/module-catalog/` (dropped page),
   `/neuralspotx/contributing/releases/` (new successor),
   `/neuralspotx/reference/public-api/` (merged into the generated reference),
   `/neuralspotx/getting-started/first-app/` (identity, must be a page and not
   a stub).
5. **404.** A made-up path under `/neuralspotx/` serves the real 404 with Home
   and Reference links, and does not redirect to Home.
6. **Catalog JSON.** `/neuralspotx/modules/catalog.json` returns 50 records and
   `/neuralspotx/modules/boards.json` returns 17 boards, both as
   `application/json`.
7. **llms content.** `/neuralspotx/llms.txt` lists all eleven machine-readable
   artifacts and every one resolves; `/neuralspotx/llms-full.txt` is about
   477 KiB and contains a signature from the Python API, an option table row
   from a CLI page and a version line from a module page, which is the
   composition the postbuild pass exists to guarantee.
8. **One public site.** The old MkDocs routes no longer serve their old content,
   and nothing links to a `site/`-built page.

Then, and only then, the owner's final review before the cutover is called done
(#261 acceptance, last box).

## 9. Not in this PR

Still to do before merge:

- Visual review, desktop and mobile, light and dark. The plan schedules it here;
  it has not happened.
- Making "Build and validate" a required check on `main`. It is the only job
  that runs the reference-completeness and public-surface tests, so a change
  that breaks the public surface can merge on a green `ci.yml` today. This is a
  branch-protection setting, so it is the owner's to make.

The helia-ui pin has moved from commit `266f614` to the released tag
`v0.1.0-alpha.16`. That release closed #143 and #149, so the component-link
recovery pass in `publish-agent-bundle.mjs` and the clone-and-replace before
play in `JourneyWalkthrough.astro` both came out. Two "Read more:" rows on Home
went with them, the HELIA stack row and the Documentation row, because the
`LinkCard` grids above them now reach the rendition with their titles, targets
and descriptions intact. The rows over the `Card` plus `CardHeader` grids stay:
those cards state their title as children rather than as a literal `title`
prop, and the pass emits a link only for a component carrying both.

Deliberately out of scope, by owner decision on 2026-09-20: Windows execution is
waived for this pass, the four hardware transcripts ship as described output
until someone captures them on a connected `apollo510_evb`, the onboard J-Link
claim stays out, and the migration matrix labels stand.

Deferred with a tracking issue: splitting the Python API page that sits at 82%
of its HTML budget, and the five product findings the migration surfaced,
AmbiqAI/neuralspotx#265 to #269. `helia-dsp` stays unchecked by the drift check,
decided rather than open: it is a private repository and the docs job is not
getting a read token for it.
