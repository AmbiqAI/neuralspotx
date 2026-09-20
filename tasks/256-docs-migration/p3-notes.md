# P3 notes: discoverability and routes (AmbiqAI/neuralspotx#261, PR 1)

Branch `261-discoverability`, stacked on `260-guides`, not pushed. Scope is the
first half of #261: the agent bundle, the redirect map, the 404, the sitemap and
the checks over all of it. No deploy, no removal of the MkDocs stack, no
credentials. That is PR 2.

## 1. What the bundle contains and how it is composed

`discoverability.llms` is on, so the plugin writes `/llms.txt`,
`/llms-full.txt`, `/content-index.json` and a `.md` rendition beside every
route. It builds all four by reading `src/content/docs` off disk and deleting
every tag, which is right for prose and empties out anything generated: a CLI
page keeps its usage block and loses its option table, a Python API page keeps
the module docstring and loses every signature, a module page loses its version,
project and revision. 94 of the 149 routes are in that state, and the file count
does not move, so nothing in a build log says so.

`astro-site/scripts/publish-agent-bundle.mjs` runs as npm's `postbuild` and
re-renders those routes from the models the pages were rendered from:

| Routes | Source of the Markdown |
| --- | --- |
| `/reference/cli/<slug>/`, 35 pages | `public/reference/cli.json`, the argparse dump, plus the same `reference-notes/cli/<slug>.md` the MDX merges |
| `/reference/config/<id>/`, 4 pages | `public/reference/config.json`, the schema manifest |
| `/reference/api/<module>/`, 5 pages | `public/reference/api/llms-full.txt`, pyref's own text bundle, cut at its H1 boundaries and keyed by route |
| `/modules/<slug>/`, 50 pages | the plugin's rendition with the `ModuleCard` facts prepended from `src/data/modules.json` |

The option and field tables are rebuilt through the same `rows()` functions the
MDX generators use, which are now exported from `scripts/lib/render-cli.mjs` and
`scripts/lib/render-config.mjs`. That is the point of the exercise: a table that
only ever existed as a `rows={...}` prop cannot be recovered by stripping the
MDX or the HTML, so the bundle is composed from the model instead. heliaRT
reached the same conclusion and carries the same postbuild pass for its
reference section.

An authored page is not automatically safe either. `componentCards()` reads
`title`, `href` and `description` back out of `LinkCard`, `Button` and `Card`
props and puts each card back under the heading the source files it under, in
source order, one entry per card. Deduplicating by href was wrong: `/modules/`
has seven cards pointing at the catalog, one per module type, and collapsing
them left a single link labeled "Backend specific" under two empty headings.
Home has no Markdown headings at all, so its nine cards land in a `## Links`
section at the end. The per-module `reference.json` link is also added to each
Python API rendition, because pyref's bundle does not carry it and it is the
artifact an agent should read instead of the page.

Every pass replaces rather than appends. Each block it writes is fenced by
`<!-- nsx:facts -->` or `<!-- nsx:cards -->` markers and the `## Machine-readable`
section is rebuilt, so running the composer twice over one `dist` produces the
same bytes. That is asserted, not assumed: the check hashes the renditions and
both llms files, runs the composer again, and fails on any change. An appending
pass would double every module's facts block and every assertion below would
still pass on the doubled file.

The 404 comes out of `content-index.json`, its rendition, llms.txt and
llms-full.txt together. The plugin indexes `/404/` as a content route and writes
it a rendition while its own checker excludes `404.html` as not one; an agent
reading the bundle has no use for the page that says a page is missing. All four
removals are one change because `helia-ui-check-discoverability` reads
`content-index.json` and requires a llms.txt line for every route in it, so
dropping the line alone just moves the inconsistency into a failing check. The
real 404 page itself, `dist/404.html`, is untouched and still checked.

`llms-full.txt` is then recomposed from the renditions on disk, in the plugin's
sidebar order, with its `<!-- url -->` section markers kept so the file reads as
one format whichever pass wrote a given section. 481 KiB, 149 sections, one per
content route.

`llms.txt` keeps everything the plugin wrote and gains a `## Machine-readable`
section, because the plugin has no hook for extra entries. Eleven artifacts:
`llms-full.txt`, `modules/catalog.json`, `modules/boards.json`,
`reference/api/reference.json`, `reference/api/llms-full.txt`,
`reference/reference.txt`, `reference/cli.json`, `reference/config.json`,
`reference/python-symbols.json`, `content-index.json` and `build-info.json`.
The composer fails if any of them is missing from `dist`, so the list cannot rot
into a set of dead links.

## 2. Checks

`scripts/check-discoverability-output.mjs`, wired into `npm run validate` ahead
of the package's own `helia-ui-check-discoverability`. Everything it asserts is
about content, because a check that counts files passes the build this phase
exists to catch.

Bundle, keyed by route rather than searched across the corpus. A whole-file
substring search is not a completeness check: `nsx-audio` is named on a dozen
other pages, so deleting its page leaves `bundle.includes('nsx-audio')` true and
the build green. llms-full.txt is cut at its section markers and each fact is
asserted against the section it belongs to:

- every name in `python-symbols.json`, inside its own module's section.
  `python-symbols.json` is generated from `neuralspotx.__all__` and pinned to it
  by `tests/test_reference_generation.py`
- every command and subcommand in the argparse dump, in its own page's section,
  which must open on `# nsx <name>`
- every module in the snapshot, in its own page's section
- an option row per flag and a field row per schema field, in that page's
  section, matched as a Markdown table row rather than as prose mentioning the
  flag
- one section per content route and no section that is not one, neither file
  mentioning the 404, and each listed artifact present in `dist`
- the composer is idempotent

Renditions, per route:

- the rendition exists, opens on the same H1 the HTML shows, and contains every
  internal link in the page's article
- a page carrying N link cards renders as N entries, each with its own title
  pointing at its own href, so a future dedupe is a failure
- no `export const`, no JSX comment, no component markup, scanned outside fenced
  code so a docstring may still show a placeholder such as `<ISO 8601 UTC>`

Four mutations were run against a good `dist` to prove the checks bite: deleting
`dist/modules/nsx-audio/`, deleting only its `content-index.json` entry,
collapsing the ten `/modules/` cards to three, and doubling the
`## Machine-readable` section. Each fails, and the first three name the route.

Redirects, 404, sitemap and JSON-LD are described in the sections below.

## 3. Redirect table and its source

`astro-site/src/data/redirects.json` holds all 67 routes the MkDocs site
publishes, authored from the fate table in section 1 of `p2-content-map.md`.
Astro's config filters the identity entries out and emits meta-refresh stubs for
the rest, because Astro refuses a redirect that collides with a page.

- 67 entries, 7 of them identity, 60 stubs in `dist`.
- MkDocs builds a directory URL per file, so the 67 files under `docs/` are the
  67 routes. One correction against the fate table: `architecture/overview.md`
  publishes at `/architecture/overview/`, not `/architecture/`, because there is
  no `architecture/index.md`. The map uses the route MkDocs actually serves.
- A page that was split maps to its primary target. `first-app` kept its path,
  so it is an identity entry and the two pages split out of it are reached from
  it.
- There is no blanket fallback. `check-discoverability-output.mjs` fails on any
  entry whose target is not in `dist`, and on any non-identity entry that emits
  no stub, so an unmapped route is a build failure.

Seven old pages have no published successor. They point at the nearest published
page rather than at Home, and each is an owner decision rather than a settled
one:

| Old route | Points at | Why, and what would change it |
| --- | --- | --- |
| `/contributing/` | `/guides/` | The Contribute group has no overview page. If one is written, point here at it. |
| `/contributing/docs-workflow/` | `/guides/contribute/agent-guidance/` | The fate table keeps this page, rewritten for Astro, as open question 4. Until it is written there is no docs-workflow page to land on. |
| `/contributing/repo-layout/` | `/guides/contribute/agent-guidance/` | Maintainer content, unpublished. |
| `/contributing/releases/` | `/reference/` | The fate table splits the versioning policy out to `/reference/releases/`, which is not written yet. |
| `/contributing/module-coverage/` | `/modules/` | Maintainer content, superseded by the generated catalog. |
| `/architecture/design-decisions/` | `/guides/concepts/` | Maintainer content, unpublished. |
| `/architecture/sdk-upstream-plan/` | `/guides/modules/sdk-providers/` | Maintainer content, unpublished. |

`/architecture/board-coverage/` points at `/modules/boards/`, which the fate
table already calls the user-facing successor, so it is not on that list.

Three of the seven are being resolved on `261-cutover`, which adds a Reference
"Releases and versioning" page and repoints `/contributing/releases/`,
`/contributing/docs-workflow/` and `/contributing/repo-layout/`. This branch
leaves `redirects.json` alone so the two do not collide.

### The module catalog's anchors

`/user-guide/module-catalog/` redirects to `/modules/catalog/`. Its twenty
anchors are all lost, and none of them is recoverable: a fragment never reaches
the server, and a meta-refresh stub navigates to a URL that carries no fragment
of its own, so there is nothing for a redirect to act on. Recovering them would
need a client-side hash router on the catalog page, which is site-local script
for a page the catalog's own filter already replaces.

Lost, with what answers them now:

| Old anchor | Where the same question is answered |
| --- | --- |
| `#all-modules` | the catalog table, which renders all 50 rows with or without the filter |
| `#module-families`, `#sdk-provider-modules`, `#sdk-wrapper-and-platform-integration-modules`, `#board-modules`, `#runtime-and-helper-modules`, `#profiling-and-instrumentation-modules`, `#external-first-class-modules`, `#npu-ml-acceleration-modules`, `#peripheral-and-bus-modules`, `#wireless-ble-modules` | the catalog's type filter, and the type groups on `/modules/` |
| `#cross-repo-module-dependencies` | each module page's Requires section |
| `#what-first-class-means`, `#what-is-not-first-class-yet` | not reproduced; the catalog states what each manifest declares and does not grade modules |
| `#working-with-modules`, `#add-a-module-to-your-app`, `#inspect-a-module`, `#search-by-keyword`, `#remove-a-module` | `/guides/modules/using-modules/` and `/reference/cli/module/` |
| `#related-pages` | the sidebar |

## 4. The 404, the sitemap and JSON-LD

The 404 written in P0 is unchanged and now checked. It is a real page with links
to Home, Getting started, Guides, Modules and Reference and an issue link; it
carries no timed redirect, and its canonical points at the site root rather than
at `/404/`, which is never built. The check fails on a `http-equiv="refresh"` in
`404.html`, on a missing canonical, and on the Home or Reference link going
away.

Starlight installs `@astrojs/sitemap` itself, so `sitemap-index.xml` and
`sitemap-0.xml` come out without extra configuration and the plugin writes the
`robots.txt` that points at the index. Verified and checked: 149 locations, all
under `https://ambiqai.github.io/neuralspotx/`, the 404 absent, every redirect
stub absent, and every content route present.

JSON-LD stays on. helia-ui serializes the graph with `JSON.stringify` straight
into a `<script>` block with no escaping, which is gaps-259 Draft 6, so a
description carrying `</script` would break out of the block. The check fails
closed on the input instead: no page description may contain `<`, `>` or
`</script`, and every emitted block must parse. The module generator already
strips those characters from manifest prose, so the rule holds today and the
check is what keeps it holding.

## 5. Provenance and budgets

The footer already carries the package version and the source commit, and
`check-output.mjs` already reads `dist/build-info.json` back and fails when the
commit is not a 40-character hash, the version is missing, or either is absent
from the rendered footer. `build-info.json` is also listed in llms.txt now, so
an agent can name the commit it read the docs at.

Per-page budgets are unchanged: 640 KB HTML and 40 KB gzip for Python API pages,
250 KB and 40 KB elsewhere, warning at 80 percent.
`reference/api/neuralspotx/api` sits at 82 percent of its HTML budget and 84
percent of its gzip budget and is warning, as designed, so it gets split before
it fails. The job summary already timed reference generation, the snapshot
check, module generation and the build; it now also records the redirect stub
count, the rendition count, the size of `llms-full.txt` and the total artifact
size.

## 6. Measurements

Local, macOS, Node 24.12.0.

| Measure | Value |
| --- | --- |
| Routes | 150 indexed, of which 149 are content routes; the 404 is not one |
| HTML files in dist | 210, that is 149 content pages, the 404 and 60 redirect stubs |
| Markdown renditions | 149 |
| Renditions rebuilt from a model | 94 |
| Renditions given back their link cards | 2, carrying 19 cards |
| `llms-full.txt` | 481 KiB, 149 sections |
| Public symbols asserted in the bundle | 80 |
| CLI commands asserted | 35 |
| Modules asserted | 50 |
| Redirect entries | 67, of which 60 emit a stub |
| dist | 718 files, 21.9 MiB |

## 7. Left for PR 2

The deploy job, the freshness guard, and the removal of `mkdocs.yml`,
`docs/stylesheets`, `docs/javascripts`, `deploy-pages.yml` and the zensical and
mkdocs-material dependencies. `docs/**` stays in the workflow's path filters
because `build-examples.mjs` reads `docs/examples/*.md`; nothing in the redirect
map depends on `docs/` or `mkdocs.yml` at build time, so `mkdocs.yml` was not
added to the filters.
