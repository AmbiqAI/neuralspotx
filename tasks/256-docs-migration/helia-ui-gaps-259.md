# helia-ui gaps found during P1b (issue #259)

Drafts only. Nothing below has been filed; Adam files or discards each one.
Checked against `v0.1.0-alpha.14`, the pinned version and still the latest
release (`gh release list -R AmbiqAI/helia-ui`: alpha.14 on 2026-09-19,
alpha.13, alpha.12).

Open upstream issues this phase touches, none of them a fit as shipped:

| Issue | Title | Why it is not the answer here |
| --- | --- | --- |
| #24 | FilterRail: facet groups that filter a grid without a framework | Closest match, still unshipped. Draft 1 asks whether a table is in scope. |
| #79, #40 | ChipRow part for logo rails and tag lists | Astro-only. Draft 3 is the React side. |
| #74 | Reference generators: grouping config and a rendered group index | Affects `RefIndex`, not a catalog. |
| #66 | Gap analysis: parts a real developer hub and product docs need | Parent. Drafts 1 to 3 belong under it. |

What NSX ended up writing locally, and why:

| NSX component | Reason |
| --- | --- |
| `astro-site/src/components/ModuleIndex.astro` | Builds the catalog's rows from the module snapshot and mounts the island |
| `astro-site/src/components/ModuleBrowser.tsx` | Drafts 1 and 7: the toolbar the package has no part for, assembled from `react/input`, `react/select`, `react/button` and the table parts |
| `astro-site/src/components/ModuleCard.astro` | Composed from the package's `Card`, `CardHeader`, `CardContent` and `Chip`; no gap, recorded for completeness |

Everything else on the Modules section is a package part or plain Markdown:
`Card`, `CardGrid`, `LinkCard`, `Chip`, and Starlight's own asides and tables.

---

## Draft 1: no faceted filter over a table

**Title:** A faceted filter that drives a table, not only a reference index

**What happened.** The module catalog is fifty rows with six filters: type,
SoC, board, toolchain, capability and free text. `astro/DataTable.astro` has
`pageSize` and nothing else. `react/data-table.tsx` has opt-in sorting and
pagination and no filtering. `react/ref-index.tsx` is the one faceted control
in the package, and its row type is
`{ id, name, kind: SymbolKind, module, group, href, summary, facets }` with
fixed columns, so using it for modules would mean calling a module type a
`SymbolKind` and a project a `module`.

**Expected.** A part that takes rows, a column set and facet definitions, and
filters client side, without the vocabulary of a generated reference.

**Source location.** `astro/DataTable.astro`, `react/data-table.tsx`,
`react/ref-index.tsx`, `ref-index-model.ts`.

**Proposal.** Either widen #24 (FilterRail) to cover a table rather than a grid,
or split `RefIndex` into a generic `FacetedTable` (rows, columns, facets,
search) plus the reference-specific row builder that already lives in
`ref-index-model.ts`. The second is a refactor of shipped code and would give
`RefIndex` and a catalog one implementation.

**NSX workaround.** `RefIndex` was tried first and rejected on sight: see
draft 7. The catalog now mounts `ModuleBrowser.tsx`, a toolbar assembled from
`react/input`, `react/select`, `react/button` and the table parts, with
Tailwind utilities for layout and no CSS of its own. It is about a hundred and
fifty lines, and every one of them is the filtering logic a `FilterRail` or a
`FacetedTable` would own. The static Markdown table stays below the island and
is hidden once the island renders, because it is what the rendition, Pagefind
and a reader without JavaScript get.

**What the part would need.** Rows, a column set, a facet set rendered as
dropdowns rather than chips, a sort control, a live count, a clear control and
an optional detail row. That is #24 widened from a grid to a table, and it is
the same shape heliaCORE's `KernelBrowser.tsx` and heliaRT's `OperatorBrowser`
each wrote for themselves: three products, three implementations, one part
missing.

---

## Draft 2: DataTable cells are plain strings

**Title:** `DataTable` cannot put a link, a chip or code in a cell

**What happened.** `astro/DataTable.astro` takes
`rows: readonly (readonly string[])[]`. A catalog row needs the module name as
a link to its page and the project as a link to its repository, and wants a
chip for the type. With string cells the only options are to drop the links or
to pass raw HTML, which the Props type does not allow.

**Expected.** A cell that can carry markup: `string | AstroNode`, or a slot or
render function per column.

**Source location.** `astro/DataTable.astro`, Props interface.

**Proposal.** Accept `readonly (readonly CellValue[])[]` where
`CellValue = string | { text: string; href?: string }`, which covers the link
case without turning the part into a render-prop API. A chip tone per column
would cover the rest.

**NSX workaround.** A plain Markdown table, which also turned out to be what
the Markdown rendition and Pagefind need.

---

## Draft 3: no React counterpart for Chip and Badge

**Title:** Astro `Chip` and `Badge` have no React equivalent, so an island
cannot use the shared vocabulary

**What happened.** The catalog's filter is a React island. Its facet controls
are chips, but `astro/Chip.astro` cannot be rendered inside one, and
`react/badge.tsx` is a shadcn `Badge` with its own variants rather than the
`.helia-chip` recipe the Astro part renders. The island ended up styling its
own toggles with Tailwind utilities and Starlight `--sl-color-*` variables,
which is a second implementation of a shipped visual.

**Expected.** The same chip in both renderers, so an island and a page put the
same thing on screen.

**Source location.** `astro/Chip.astro`, `astro/Badge.astro`,
`react/badge.tsx`, `recipes.css`.

**Proposal.** Ship `react/chip.tsx` rendering the same `.helia-chip` classes
with the same `tone` and `size` props, and a pressed state for filter use.
This is the React half of #79 and #40, which cover the Astro layout part.

**NSX workaround.** None now: the catalog's chips are `RefIndex`'s own, which
are Tailwind utilities in the package rather than the `.helia-chip` recipe. The
gap stands for any island that is not `RefIndex`.

---

## Draft 4: the spelling check has no site-extensible generated-file list

**Title:** `check-spelling` cannot be told that a generated file quotes upstream
text

**What happened.** The generated module pages quote `nsx-module.yaml` prose
verbatim, and one module manifest spells a capability `serialisation`. The
check fails. It already has the concept:
`scripts/check-spelling.mjs` holds `const GENERATED = ['THIRD-PARTY-NOTICES.md',
pkg('THIRD-PARTY-NOTICES.md')]` for exactly this reason, but the list is
hardcoded in the package and a site running `--root .` cannot add to it. The
only escape is per line, and the escape text survives into the page's Markdown
rendition, so applying it broadly puts `{/* spelling: allow */}` in front of an
agent on every quoted line.

**Expected.** A site can name its own generated paths, the way it names its
root.

**Source location.** `scripts/check-spelling.mjs`, `GENERATED` and `SKIPPED`;
`scripts/lib/scope.mjs`, `IGNORED_DIRS`.

**Proposal.** A repeatable `--generated <glob>` flag, or a
`helia-ui.checks.json` at the root listing generated paths that both
`check-spelling` and `check-spdx` read. A glob is enough;
`src/content/docs/modules/**` is the whole ask here.

**NSX workaround.** An explicit `QUOTED_TERMS` list in
`astro-site/scripts/build-modules.mjs`, marking only the values that need it,
with `<span data-quoted="spelling: allow" />` rather than an MDX comment so the
mark does not reach the rendition (draft 5). It fails closed: a manifest
introducing a new British spelling fails the site's spell check until somebody
looks at it.

---

## Draft 5: Markdown renditions keep MDX expressions

**Title:** The Markdown rendition drops components but prints `{/* ... */}`

**What happened.** With `discoverability.markdown` on, a page's `.md` rendition
strips JSX elements, which is the documented behavior, but leaves MDX
expression nodes in the text. A comment expression, which renders nothing in
HTML, appears verbatim in the rendition an agent reads.

**Expected.** An expression that renders nothing renders nothing in both
outputs. At minimum, comment expressions elided.

**Source location.** The discoverability plugin's Markdown rendition pass
(`starlight/`), observed in `dist/modules/catalog/index.md`.

**Proposal.** Drop `mdxFlowExpression` and `mdxTextExpression` nodes whose
value is only a comment. The wider question, whether a rendition should carry
what a component rendered rather than dropping it, is heliaRT's lesson recorded
in `tasks/256-docs-migration/plan.md` §1 and is bigger than this.

**NSX workaround.** The marker is an empty inline element instead of an
expression. Tags are dropped from the rendition, so nothing reaches it. The
same pass drops an escaped `\<img src=x\>` as though it were a tag, which is
why manifest prose is escaped with character references rather than
backslashes.

---

## Draft 6: the JSON-LD block escapes nothing

**Title:** `discoverability.jsonLd` writes a page description into a script
body without escaping it

**What happened.** A generated module page takes its description from another
repository's `nsx-module.yaml`. With `jsonLd` on, the description is written
into `<script type="application/ld+json">` as-is: a description containing
`</script>` ends the block and everything after it is markup the browser
parses. Observed on a fixture page, where
`"description":"Summary <img src=x onerror=alert(1)> ..."` reached the built
JSON-LD verbatim. The meta attribute on the same page is escaped correctly, so
the two paths disagree.

**Expected.** A string written into a JSON-LD script has `<` escaped, which is
what `\u003c` is for; nothing a page's frontmatter says should be able to end
the block.

**Source location.** `starlight/discoverability.ts`, the JSON-LD serialization
that feeds `Discoverability.astro`.

**Proposal.** Serialize with `JSON.stringify(...).replace(/</g, '\\u003c')`, the
standard treatment for JSON in a script element. It changes no rendered output.

**NSX workaround.** `metaText` in `astro-site/scripts/build-modules.mjs` drops
angle brackets from a page description before it is written, because the site
cannot escape for a consumer it does not control.

---

## Draft 7: RefIndex is a reference index in its wording and its controls

**Title:** `RefIndex` cannot be labelled, and chip facets do not scale past a
dozen values

**What happened.** `RefIndex` rendered the module catalog correctly and was
rejected on sight, because a chip per value is a control that only works while
the values are few. The catalog's board facet is seventeen values, its SoC
facet eleven and its capability facet about a hundred; the reader scrolled
three screens of chips to reach the table. A dozen values is the most a row of
chips holds before it stops being a row.

These are the rest of what a reader saw that a catalog would not:

- The count reads `50 of 50 symbols`, from `{visible.length} of {rows.length}
  symbols` (`react/ref-index.tsx`). There is no prop for the noun.
- The first column header is `Symbol`. There is no prop for it, or for the
  `Summary` header.
- Facet order is the package's: known ids by rank, then alphabetical by id
  (`refIndexFacets` in `ref-index-model.ts`). A catalog wants Type first; it
  gets Board, Capability, SoC, Toolchain, Type.
- The same array drives the chips and the table columns, so a facet cannot be
  filterable without also being a column.
- There is no collapsed or limited facet, and no way to ask for a dropdown
  instead of chips.
- No state reaches the URL. A link cannot open the index with a facet selected
  and a reader cannot share what they are looking at, so the overview's type
  cards link to the catalog rather than to a selection of it.
- `RefIndexContract` is kernel-shaped: `prerequisites`, `bufferSize`,
  `tolerances`, `notes`. A module has capabilities, use cases and constraints,
  of which only two map honestly.
- `kind: SymbolKind` is required and never rendered.

**Expected.** The vocabulary is the consumer's: a noun for the count, labels
for the first two columns, an order for the facets, and a facet that can be
collapsed when it has more values than a row of chips.

**Source location.** `react/ref-index.tsx` (count, headers, facet rendering),
`ref-index-model.ts` (`refIndexFacets`, `RefIndexRow`, `RefIndexContract`).

**Proposal.** Add `noun`, `columns: { name, summary }`, an optional facet order,
a `control: 'chips' | 'select'` or a `collapsedAt` on `RefIndexFacet`, `kind`
optional, and query-string state for the selection. None of it changes a
reference index that passes nothing. The control question is the one that
matters: chips and a dropdown are the same facet at different sizes, and only
the part knows how many values there are.

**NSX workaround.** `ModuleBrowser.tsx`. The cost of not using `RefIndex` is
the filtering logic, about a hundred and fifty lines, and the island's
JavaScript: 350 KB against `RefIndex`'s 258 KB, because `react/select` brings
Radix's select, portal and dismissable-layer with it.

---

## Draft 8: a package React island is not in the consumer's Tailwind scan

**Title:** Using a `react/` part means knowing to add a `@source` glob for it

**What happened.** `starlight-tailwind.css` documents that the scan list is the
consumer's, and the site listed the package's `astro/` and `starlight/`
directories. Mounting `react/ref-index` produced a working, entirely unstyled
island: the chips were boxes and the search field a bare input, because every
class the component names is in `node_modules` and nothing scanned it.

**Expected.** The failure is silent and looks like a broken component rather
than a missing glob. Either the package's own `@source` covers its React parts,
or the README says the glob is required with the parts it applies to.

**Source location.** `tailwind.css` (the scan-list comment),
`starlight-tailwind.css`, `react/*.tsx`.

**Proposal.** Document the glob next to the React exports, or ship it: a
`@source` in the package resolves against the file that declares it, which is
in `node_modules`, so `@source '../react/**/*.tsx'` from the package's own CSS
would cover it without a consumer edit.

**NSX workaround.** One line in `astro-site/src/styles/tailwind.css`.
