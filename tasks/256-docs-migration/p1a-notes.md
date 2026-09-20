# P1a: generated reference (issue #258)

## What runs

`astro-site/scripts/build-reference.mjs`, wired into `prepare:docs` so it runs
before every `dev`, `check` and `build`. Three areas in one pass:

| Area | Extraction | Render |
| --- | --- | --- |
| Python API | `griffe dump neuralspotx --docstyle google -f` (griffe 1.7.3, via `uv run --with`) then `scripts/docs/prune_griffe.py` | `helia-ui-pyref` |
| CLI | `scripts/docs/dump_cli.py` walks the argparse tree | `astro-site/scripts/lib/render-cli.mjs` |
| Configuration | `scripts/docs/dump_config.py` reads `scripts/docs/config_schema.yaml` | `astro-site/scripts/lib/render-config.mjs` |

Nothing generated is committed. `astro-site/.gitignore` covers the three MDX
directories under `src/content/docs/reference/`, `src/data/reference-*.json`
and `public/reference/`.

## Measured

Local, macOS, from a warm uv cache:

| Stage | Duration |
| --- | --- |
| griffe dump | 534 ms |
| prune griffe | 139 ms |
| pyref | 59 ms |
| dump cli | 121 ms |
| render cli | 4 ms |
| dump config | 75 ms |
| render config | 1 ms |
| generation total | ~0.9 s |
| `npm run build` end to end | ~3.2 s, 53 pages |

Counts: 80 Python symbols on 6 pages, 35 CLI pages (18 distinct commands, 14
subcommands, 3 aliases) plus an index, 4 configuration schemas plus an index.
15 CLI pages carry merged hand-written notes. Unresolved cross-references: 0.
Largest page `reference/api/neuralspotx/api` at 493,110 bytes HTML and 31,111
bytes gzip.

## Decisions

**The griffe dump is pruned before pyref sees it.** `prune_griffe.py` resolves
every `__all__` name through its alias chain to the concrete definition,
rehomes it onto the public module that re-exports it, drops private modules
entirely, and retargets docstring cross-references onto the new paths. This is
the interim workaround for helia-ui#120 (the `--filter` is members-only, so a
raw dump emitted 59 private `_module` pages) and helia-ui#121 (chained
re-exports left 105 unresolved references). Both upstream issues are open and
alpha.14 is still the newest release, so there was no version to bump to.
Delete the workaround when they land.

**Homing is declared, not inferred.** `HOME_MODULES` lists the public modules a
symbol may be documented under, and a symbol only lands there if the module's
own `__all__` re-exports it. Errors and the emitter are pinned to the package
root because they are defined in private modules. `tests/test_reference_generation.py`
asserts every anchor resolves to the same object as `neuralspotx.<name>`.

**Grouping lives in the sidebar, not in the page tree.** #258 asks for pages
grouped as errors, models, functions and emitters. pyref emits one page per
module and offers no grouping control (helia-ui#74), and a synthetic
category-per-module tree made the largest page bigger (668 KB versus 493 KB)
without being an importable path. So the pages stay on real module paths and
`build-reference.mjs` builds a category-grouped sidebar with symbol-level deep
links from the catalog `prune_griffe.py` emits. The four groups are there; the
pages behind them are not one-per-group.

**Provisional appears once per page.** pyref has no stability field, so
`build-reference.mjs` injects a Starlight `banner` into each generated page's
frontmatter after pyref writes it.

**Budgets are split by area.** Gzip is held at the helia-rt figure of 40 KB for
every page and is the binding constraint. The uncompressed budget is 250 KB for
CLI and configuration pages but 550 KB for Python API pages: a Starlight page
shell measures about 100 KB before any content, and a rendered Python signature
with its parameter table costs roughly 10 KB, so 250 KB would cap a page at
about ten symbols and break any sensible grouping. **This is a deviation from
the 250 KB starting point in the brief and needs a decision.**

**Configuration tables come from a manifest.** Only `board.yaml` and the lock
are backed by dataclasses; `nsx.yml` keeps unknown keys in `extra` and
`nsx-module.yaml` validates imperatively, so the field tables cannot be
introspected. `scripts/docs/config_schema.yaml` holds them and the tests push
each documented example through the real loader, then remove one documented
required field at a time and assert the loader objects. Writing that test
found two manifest claims that were wrong: the lock reader defaults a missing
`schema_version` and returns an empty lock for missing `targets` rather than
raising, so the manifest now says so.

## Stable published paths

| Path | Contents |
| --- | --- |
| `/reference/api/reference.json` | the whole pyref model |
| `/reference/api/<module>.json` | per-module model |
| `/reference/api/llms.txt`, `/reference/api/llms-full.txt` | pyref text bundles |
| `/reference/reference.txt` | combined bundle: every symbol, command and field |
| `/reference/cli.json` | the argparse tree |
| `/reference/config.json` | the configuration schemas |
| `/reference/python-symbols.json` | symbol catalog with categories |
| `/reference/report.json` | counts, timings, anchors, routes |

## Checks

- `tests/test_reference_generation.py`: 22 tests covering `__all__` coverage,
  anchor resolution, private-path leakage, unresolved references, the full
  argparse tree, alias dispatch, per-command pages and options, and the four
  configuration schemas against their loaders. `tests/test_public_surface_doc.py`
  is untouched and still passes.
- `astro-site/scripts/check-reference-output.mjs`, wired into `npm run validate`:
  anchor presence and uniqueness in the built HTML, every route present, no
  private path published, per-area HTML and gzip budgets, every symbol, command
  and schema present in the text bundle, and every published artifact present.

## Not done

- The MkDocs docs under `docs/` are untouched and stay live until #261.
  `docs/reference/public-api.md` was not retired; the issue asks for that, the
  P1a brief says to leave it.
- Prose for the Reference section beyond the index and the merged CLI notes is
  #260.
- Two source docstrings changed: a fenced code block in
  `src/neuralspotx/nsx_lock/__init__.py` (the indented form broke the MDX
  compile) and two British spellings the site spell check rejected.
