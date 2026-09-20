# helia-ui gaps found during P3, discoverability (issue #261)

Drafts only. Nothing below has been filed; Adam files or discards each one.
Checked against the pin in `astro-site/package-lock.json`.

Two drafts from P1b cover ground this phase walked again and are not repeated
here:

| Draft | Where | Status in P3 |
| --- | --- | --- |
| gaps-259 Draft 5, Markdown renditions keep MDX expressions | `starlight/discoverability.ts` | Confirmed on four CLI pages, whose `{/* TODO(#260): ... */}` notes reached `dist/<route>/index.md` as page text. `scripts/check-discoverability-output.mjs` now fails on it and `publish-agent-bundle.mjs` strips it. |
| gaps-259 Draft 6, the JSON-LD block escapes nothing | `starlight/discoverability.ts` | Confirmed. Worked around by checking the input rather than the output: no page description may carry `<`, `>` or `</script`. |
| gaps-260 Draft 5, `export const` bodies leak and `LinkCard` content vanishes | `starlight/discoverability.ts`, `stripEsm` and `reduceTags` | Both confirmed again on Home and `/modules/`, with the `description` prop lost as well. Recorded as a second instance in that draft rather than repeated here; the workaround and its check are named there. |

---

## Draft 1: the llms bundle is built from authored source, so generated pages arrive empty

**Title.** `discoverability`: llms.txt, llms-full.txt and the Markdown renditions
lose every page whose content lives in component props

**What happens.** `collectSources()` reads `src/content/docs` off disk and
`renderMarkdown()` removes each tag and keeps the text between tags. A page
whose content is a prop has no text between tags, so the rendition is the front
matter title and whatever prose sits outside the components.

Measured on this site, before the workaround:

| Route | Rendition | Same route rebuilt from the model |
| --- | --- | --- |
| `/reference/api/neuralspotx/` | 3,380 bytes, no signatures | 8,023 bytes |
| `/reference/cli/build/` | usage block only, no `RefParams` table | usage plus a 10-row option table |
| `/modules/nsx-core/` | no version, project, revision or source URL | all four |

94 of this site's 149 routes are affected, which is every page the reference and
module generators write. The file count does not change, so a completeness check
that asserts files exist reports a healthy build.

**Expected.** Either the rendition is produced from the rendered page rather
than the source, or the plugin offers a hook that lets a site supply the
Markdown for a route it generated.

**Source location.** `starlight/discoverability.ts`, `collectSources()`,
`renderMarkdown()`, and the `astro:build:done` writer.

**Workaround here.** `astro-site/scripts/publish-agent-bundle.mjs` re-renders
those routes from the argparse dump, the schema manifest, pyref's text bundle
and the module snapshot, then recomposes `llms-full.txt`. heliaRT does the same
thing for its reference section in `publish-reference-markdown.mjs`, so this is
the second site to carry the same postbuild pass, which is the argument for the
hook.

---

## Draft 2: no hook for extra llms.txt entries

**Title.** `discoverability`: llms.txt cannot list a site's machine-readable
artifacts

**What happens.** llms.txt lists routes. A site that publishes a catalog JSON, a
reference model and a text bundle has no way to tell an agent they exist, which
is the one thing an agent would rather read than the pages.

**Expected.** An option that takes extra sections, or a documented convention
for appending to the file after `astro:build:done`.

**Source location.** `starlight/discoverability.ts`, the llms.txt writer.

**Workaround here.** `publish-agent-bundle.mjs` appends a `## Machine-readable`
section listing eleven artifacts.

---

## Draft 3: the 404 is indexed as a content route

**Title.** `discoverability`: `content-index.json` and llms.txt list `/404/`

**What happens.** The plugin's own `check-discoverability.mjs` excludes
`404.html` from the routes it checks, on the stated grounds that Astro's 404 is
not a content route. The index it checks against lists it anyway, with a
rendition at `/404/index.md` and a line in llms.txt, and there is no
`dist/404/index.html` behind either.

**Expected.** One answer in both places.

**Source location.** `starlight/discoverability.ts` against
`scripts/check-discoverability.mjs`.

**Workaround here.** `publish-agent-bundle.mjs` removes the route from
`content-index.json`, deletes its rendition, and drops it from llms-full.txt and
llms.txt. All four together, because the package's own checker reads
`content-index.json` and requires a llms.txt line for every route in it: taking
the line out on its own turns the inconsistency into a failing check.
`check-discoverability-output.mjs` then asserts that neither llms file mentions
it. An agent reading the bundle has no use for the page that says a page is
missing.
