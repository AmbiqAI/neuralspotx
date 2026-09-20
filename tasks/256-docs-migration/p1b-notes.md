# P1b: module catalog, per-module pages and board matrix (issue #259)

## What runs

Two stages, split by whether they need the network.

| Stage | Command | Network | Output |
| --- | --- | --- | --- |
| Snapshot | `uv run --group docs python scripts/docs/build_module_data.py` | yes | `astro-site/src/data/modules.json`, `boards.json`, both committed |
| Section | `astro-site/scripts/build-modules.mjs`, wired into `prepare:docs` | no | MDX under `src/content/docs/modules/`, `public/modules/`, sidebar, facets and report under `src/data` |

Nothing the section stage writes is committed. `astro-site/.gitignore` covers
`src/content/docs/modules/`, `src/data/modules-{facets,sidebar,report}.json`
and `public/modules/`. The two snapshots are the exception: they are the input
the build is reproducible from.

## Generation needs the network; the build does not

Thirty-two of the fifty modules keep their `nsx-module.yaml` in another
repository. `list_modules(registry_only=True, include_metadata=True)` resolves
eighteen of them from packaged content (the seventeen board modules and
`nsx-tooling`) and reports `metadata_available: False` for the rest, so the
only way to read a complete catalog is to fetch.

`build_module_data.py` fetches each project with `git init` plus a shallow,
blobless, sparse checkout of just the manifest paths. The largest project,
`nsx-ambiq-sdk`, comes down in about 2.7 s and 556 KB of `.git`. A cold run
over all thirteen projects takes about 27 s; a warm one, reusing the clones
under `astro-site/.astro/module-sources`, takes 0.2 s. The Astro build reads
only the committed JSON and fetches nothing.

Clones are keyed by `(project, revision)`, not by project. `nsx-npu` pins
`v5.2.25` while the rest of `nsx-ambiq-sdk` sits on `v5.2.24`, so one project
can need two checkouts. Keying by project alone silently resolved `nsx-npu`
against the wrong tag, where its manifest does not exist.

## Measured

Local, macOS, Node 24.12.0:

| Stage | Duration |
| --- | --- |
| snapshot, cold (13 projects fetched) | ~27 s |
| snapshot, warm (`--check`) | ~0.2 s |
| render pages | 7 ms |
| publish artifacts | 1 ms |
| `npm run build` end to end | ~2.0 s, 105 pages |

Counts: 50 modules over 7 declared types, 53 generated pages (overview,
catalog, board matrix and one per module), 17 boards, 11 SoC families, 5
facets. Snapshots: `modules.json` 80,344 bytes, `boards.json` 16,218 bytes.
The facet props the island receives are a further 26,643 bytes, generated.

Largest page is the catalog at 138,877 bytes of HTML and 18,710 gzip, against
the 250 KB / 40 KB budget the CLI and configuration pages use: 56% and 47%.
Every other page in the section is under 97 KB, which is close to the empty
Starlight shell.

## Decisions

**The snapshot is committed and the check is what makes it trustworthy.** Owner
decision, plan §7.4. `--check` regenerates in memory and diffs. It is
mutation-tested in `tests/test_module_data_snapshot.py`: a changed version, a
removed module, an added field and a changed board tier each have to register.

**A private project cannot be told apart from drift, so it is reported instead
of failed on.** `helia-dsp` is private. A CI job with no credentials gets an
access error for it, which would otherwise compare as if every manifest field
had been deleted. `reconcile_unavailable` carries the committed fields over for
exactly those modules and names them in the run's output; everything else is
still compared, and a test proves the reconciliation does not hide a real
change elsewhere. Writing a snapshot that is missing a manifest needs
`--allow-missing`, so the committed artifact stays complete.

**The static table is the catalog; the island only hides rows.** The
acceptance criteria want the full table in the built HTML and in the Markdown
rendition with JavaScript disabled, and they want a filter. Rendering the rows
inside the island would have put fifty modules on the page twice, because the
Markdown rendition is derived from the MDX source and strips components. So the
page carries an ordinary Markdown table, the island mounts with
`client:only="react"` and toggles `hidden` on the rows it finds by module name
in the first cell, and a reader with no JavaScript sees the table and no inert
controls. The `.md` rendition carries all fifty rows.

**Budgets are the 250 KB / 40 KB class, with the same 80% warning.** Unlike the
Python API pages there was no reason to deviate: the catalog is one table and
it lands at 56% of the uncompressed budget.

**Compatibility is declared, in one wording, everywhere.** One
`:::note[How compatibility is declared]` block, emitted on the overview, the
catalog, the board matrix and every module page.
`check-modules-output.mjs` greps the rendered text of all 53 pages for
"validated on", "tested on", "verified on", "hardware validated", "known to
work on" and "proven on", and also fails a page that never says "declare" at
all. The snapshot's own manifest prose is checked the same way in pytest.

**British spellings in manifest prose are escaped, not rewritten.** One module
manifest (`nsx-nanopb`) spells a capability `serialisation`, which the site's
American-English check rejects. Rewriting another repository's words would make
the page disagree with `nsx module describe`, and helia-ui's checker has no way
for a site to mark a generated file as quoting upstream. So `build-modules.mjs`
carries an explicit `QUOTED_TERMS` list and appends the per-line escape only to
the lines that need it. Two consequences worth knowing: the escape survives
into the Markdown rendition, which is why it is applied narrowly rather than to
every manifest-derived line; and a manifest introducing a new British spelling
fails the site's spell check, which is the intended failure mode. The fix is an
issue on the module's own repository.

## Found while building this

Four dependency names in the manifests are not modules the registry pins:
`nsx-power` and `nsx-usb` both require `nsx-timer`, `nsx-uart` requires
`nsx-interrupt`, and `nsx-ethos-u-driver` optionally depends on `nsx-harness`.
`nsx-timer` and `nsx-interrupt` do exist as manifests inside `nsx-ambiq-sdk`;
they are simply absent from `registry.lock.yaml`. The catalog renders an
unknown dependency as a plain name rather than a link, and
`test_dependencies_name_modules_that_exist` pins the set of four so a fifth is
somebody's decision. Whether the registry should pin those modules is a
question for the owner, not a docs change.

The hand-written catalog's drift is resolved by construction: the page listed
52 names over 98 rows against 50 in the lock. `docs/user-guide/module-catalog.md`
and `docs/javascripts/module-catalog-tables.js` are untouched and stay live
until the cutover.

`provides`, `integrations` and `example_refs` are in the manifest schema but
empty in all fifty modules today, so the sections that would render them never
appear. They are generated, not dropped: a module that starts declaring them
gets the section without a code change.

## Stable published paths

| Path | Contents |
| --- | --- |
| `/modules/catalog.json` | the module snapshot, byte for byte |
| `/modules/boards.json` | the board snapshot |
| `/modules/catalog/` | every module as one table row, in HTML and in `.md` |
| `/modules/<name>/` | the per-module page an agent cites |
| `/modules/boards/` | the board matrix and the SoC families |

## Checks

- `tests/test_module_data_snapshot.py`: 21 tests. The snapshot against the
  registry lock, the discovery API, the board descriptors and the package's
  board order; the shape of every field; the wording; and the drift check under
  mutation.
- `astro-site/scripts/check-modules-output.mjs`, wired into `npm run validate`:
  a page and a catalog row per module, a link back to the catalog and an
  `nsx module add` snippet on each page, the static table's row count, the
  board matrix in the package's order, the wording pass, the served JSON
  against the committed snapshot, and the per-page budgets.
- `.github/workflows/docs.yml`: the drift check, the modules pytest, and the
  generation and build durations in the job summary.

## Not done

- The MkDocs pages under `docs/` are untouched and stay live until #261.
- Prose about using modules is #260.
- The board matrix carries what `board.yaml` declares and nothing more. There
  is no per-board validation matrix in this repository, and inventing one would
  be the claim the wording rule exists to prevent.
