# helia-ui gaps found during P1a (issue #258)

Drafts only. Nothing here has been filed. The pinned version is
`v0.1.0-alpha.14`, which is the latest release; `gh release list -R
AmbiqAI/helia-ui -L 5` shows nothing newer, so no version bump is available
and every gap below needed an NSX-side workaround.

Already filed and still open, both confirmed against alpha.14:

- **#120 pyref emits pages for private modules.** Confirmed: a raw dump of
  `neuralspotx` produced 79 pages, 59 of them for `_module` paths.
- **#121 chained re-export cross-references go unresolved.** Confirmed: 105
  unresolved references on the raw dump.

Both are closed on the NSX side by `scripts/docs/prune_griffe.py`, which
rewrites the griffe dump into the public surface before pyref sees it. The
result is 5 pages and 0 unresolved references. That workaround should be
deleted when #120 and #121 land.

---

## Draft 1: pyref escapes docstring content inside indented code blocks

**Title:** pyref escapes `<` and `{` inside indented code blocks, and can emit
MDX that fails to compile

**What happened.** A module docstring containing a four-space indented code
block rendered with its content escaped as prose: `&lt;board>` and
`\{ version: ... \}` appeared inside what a reader sees as a code sample.
Worse, `escapeMdx` leaves `<ISO 8601 UTC>` alone because `isElementName('ISO')`
is true, so the MDX compiler then fails with "Unexpected character after `<`,
expected a valid JSX tag" and the whole site build stops.

**Expected.** An indented code block is code, so its content should pass
through verbatim like a fenced block does. Failing that, a `<Name` that does
not open a valid element should be escaped rather than assumed to be JSX.

**Source location.** `scripts/lib/markdown.mjs`, `escapeMdx` and
`mapOutsideCode`; `mapOutsideCode` only protects inline backtick spans, so
indented blocks reach `escapeMdx` as prose.

**Proposal.** Teach `mapProse`/`mapOutsideCode` to recognize indented code
blocks alongside fenced ones. Separately, make the `<Name` case fail closed:
escape unless a matching `>` closes a syntactically valid tag.

**Workaround used.** Converted the one affected docstring
(`src/neuralspotx/nsx_lock/__init__.py`) to a fenced block. The site build
fails loudly if another docstring hits this, which is an acceptable guard but
not a fix.

---

## Draft 2: no way to group generated pages

**Title:** pyref cannot group pages or sidebar entries by anything but module
path

**What happened.** Issue #258 asks for the Python reference grouped as errors,
models, functions and emitters. pyref emits one page per module and a sidebar
fragment that mirrors the module tree, with no flag to group otherwise.

**Expected.** A way to declare groups, for example a `--group` mapping from a
pattern to a label, applied to the emitted sidebar fragment.

**Source location.** `scripts/lib/reference-render.mjs`, `buildSidebar`. This
is the same ground as the open #74 ("Reference generators grouping config and
index"), so it may be a comment on #74 rather than a new issue.

**Proposal.** Fold into #74: let the caller supply group labels and a
predicate, and emit symbol-level entries so a group can span modules.

**Workaround used.** `prune_griffe.py` emits a symbol catalog with a category
per symbol, and `astro-site/scripts/build-reference.mjs` builds its own
grouped sidebar from it. Pages stay per-module.

---

## Draft 3: no per-page stability status

**Title:** pyref has no way to mark a page or a symbol as provisional

**What happened.** All 80 names in `neuralspotx.__all__` are Provisional. The
model carries `deprecated` but nothing else, so there is no supported way to
say "this whole page is provisional".

**Expected.** Either a per-symbol `status`/`stability` field sourced from a
docstring marker, or a `--status` flag that stamps every generated page.

**Source location.** `reference-model.ts` symbol shape, and the `RefSymbol`
props in `scripts/lib/reference-render.mjs`.

**Proposal.** Add an optional `status` string to the symbol model and render it
as a badge, plus a page-level default so a caller can set it once.

**Workaround used.** `build-reference.mjs` injects a Starlight `banner` into
the frontmatter of every generated page after pyref writes it, which gives the
once-per-page placement #258 asks for.

---

## Draft 4: signature types are not linked across pages

**Title:** pyref renders a signature type as plain text when its definition is
on another page

**What happened.** `create_board` returns `BoardDescriptor`, which is
documented on the package root page. On the `neuralspotx.api` page the return
type renders as plain text four times, with no link, even though the symbol is
in the model and carries the anchor `neuralspotx.BoardDescriptor`. Linking
appears to be within-page only.

**Expected.** A type that exists in the model links to wherever it is
documented, the same way an explicit `[Text][target]` cross-reference does.

**Source location.** `scripts/lib/reference-render.mjs`, the signature
rendering path, versus the `[Text][target]` resolver at lines 173 to 189 which
does consult the whole index.

**Proposal.** Resolve identifiers in rendered signatures through the same index
the cross-reference resolver uses, and emit an anchor when the id is known.

**Workaround used.** None. `prune_griffe.py` now makes sure such types are
documented and anchored, so the information is reachable, but the signature
itself stays unlinked.
