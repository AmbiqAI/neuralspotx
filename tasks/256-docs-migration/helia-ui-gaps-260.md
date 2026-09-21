# helia-ui gaps found during P2 PR1, Getting started (issue #260)

Drafts only. Nothing below has been filed; Adam files or discards each one.
Checked against `v0.1.0-alpha.14`, the version pinned when this pass ran. Each
draft carries its own status; the pin itself lives in
`astro-site/package-lock.json`.

Nothing in this phase needed a local component. Every page is Markdown or MDX built from
package parts (`CodeTabs`, `AsciiTerminal`, `CardGrid`, `LinkCard`) plus Starlight's own
asides, tables and code blocks. Where a part fell short, the page uses plainer Markdown
rather than a workaround, so each draft below names what the page does instead.

Open upstream items this phase touches:

| Issue | Title | Status here |
| --- | --- | --- |
| #118 | `AsciiTerminal` types out `command` lines only | Hit again on five transcripts. Nothing new to add; the observation is the same one P0 filed. |
| #128 (PR) | Render Starlight asides as `Callout` | The whole section depends on it. Every `:::note`, `:::tip` and `:::caution` here renders as a plain Starlight aside until it lands, which is deliberate: no site-side styling was added to compensate. |

---

## Draft 1: CodeTabs has no PowerShell language

**Title:** `CodeTabs` and `CodeBlock`: add `powershell` to `CodeLanguage`

**What happened.** The install page carries one tab per operating system for each of three
steps. The macOS and Linux tabs are `bash`. The Windows tab is PowerShell, and
`CodeLanguage` is
`'bash' | 'c' | 'cpp' | 'diff' | 'json' | 'plaintext' | 'python' | 'sh' | 'tsx' | 'typescript'`,
so there is no honest value for it.

**What the page does instead.** The Windows tabs are `plaintext`, so they render
unhighlighted rather than being mislabeled as another shell. A comment in the page says
why, so the next author does not "fix" it to `sh`.

**Why it matters.** Any Ambiq product with a Windows install path hits this on its first
install page. `cmd` has the same problem if a product ever needs it.

**Suggested shape.** Add `powershell` to the union and to whatever grammar list
Expressive Code is configured with. Shiki ships the grammar already.

---

## Draft 2: no way to compose tabs around anything that is not a code string

**Title:** Tabs as a layout part, not only a code part

**What happened.** `CodeTabs` takes `tabs: readonly CodeTab[]` where
`CodeTab = { label, language, code }`. The content is a string that the component renders
as code. That is exactly right for the three install steps, and it is the wrong shape for
two other things the same section wanted:

1. Per-OS tabs around a transcript, so the reader sees `AsciiTerminal` output for their own
   platform. Plan section 5 already listed this as an extension candidate; this is the
   first page that actually needed it.
2. Per-OS tabs around a step that mixes prose, a link and a command, which is what the
   Windows Arm-toolchain step really is: run an installer, tick a box, open a new terminal,
   then run one command.

**What the page does instead.** The Windows toolchain and J-Link tabs put the prose in
shell comments inside the code string, which reads acceptably but is not what a comment is
for. The per-OS deep-link pages carry anything longer.

**Why it matters.** Install and setup pages are the most tab-shaped content a docs site
has, and they are rarely pure code.

**Suggested shape.** Either a slot-based `Tabs` and `Tab` pair alongside the existing
`CodeTabs`, or an optional `content` slot per tab that takes precedence over `code`. A
shared tab group name, so selecting macOS once selects it for every group on the page,
would be the natural second half of this and matches what readers expect from Starlight's
`<Tabs syncKey>`.

---

## Draft 3: AsciiTerminal cannot mark an elided region

**Title:** `AsciiTerminal`: a line kind for elided output

**What happened.** Two transcripts on this section are long enough that showing them whole
would bury the point: CMake prints twelve lines of compiler ABI detection during
`nsx configure`, and Ninja prints twenty-four steps during `nsx build`. Both needed a
visible "lines removed here" marker so a reader knows the transcript is abridged rather
than truncated or faked.

**What the page does instead.** A `muted` line whose text is hand-written, for example
`[..] (20 more compile and archive steps)`. It reads fine, but it is indistinguishable in
the DOM from a real muted output line, which matters for a site whose whole claim is that
its transcripts are captured runs.

**Why it matters.** Any product doc that shows real build output has to abridge it. If the
part cannot express the elision, every product invents its own convention and the copy
button copies the invented text as if it were output.

**Suggested shape.** An `elision` line kind rendered distinctly (a rule, or centered
ellipsis with the optional text as a label), excluded from the copy payload, and given an
`aria-label` that says the transcript is abridged.

---

## Draft 4: no Steps part for a numbered task sequence

**Title:** A `Steps` part for ordered task sequences

**What happened.** Four pages in this section are ordered procedures: install has five
numbered steps, flash and view has four. Starlight ships `<Steps>` for exactly this;
helia-ui does not, and the package's parts are the ones this site is meant to use.

**What the page does instead.** Numbered `##` headings, which is plain, works, and gives
each step an anchor and a table-of-contents entry. That last property is genuinely better
than Starlight's `<Steps>`, so this draft is the weakest of the four.

**Why it matters.** Mostly consistency. If several Ambiq products write install pages,
they should all look the same, and right now each one picks between headings, an ordered
list and Starlight's component.

**Suggested shape.** Worth a question before an issue: is a numbered-step part wanted, or
is "use headings so every step is linkable" the house style? If the latter, say so in the
package's authoring guidance and this draft goes away.

---

## Draft 5: the Markdown rendition emits `export const` bodies and drops LinkCard content

**Title:** Markdown rendition: `export const` bodies leak as prose, and attribute-only
components render as nothing

**What happened.** Two separate defects in the same pass, both found by reading the
published `.md` renditions of the Getting started pages rather than the HTML.

1. **`export const` leaks its body.** `stripEsm` in `starlight/discoverability.ts:219-241`
   drops a line when it matches `/^\s*export\s+(?:const|let|default|function)\s/`. That
   matches the first line of the statement and nothing else, so a multi-line
   `export const lines = [ ... ];` loses its opening line and publishes the remaining
   twenty as body text. Five pages were affected. The worst,
   `dist/getting-started/install/index.md`, opened with eighty lines of JavaScript object
   literals, a `//` comment among them, before the first sentence of prose.
   The multi-line `import { a, b } from '...'` form is handled by the `open` flag a few
   lines above, so the machinery for a multi-line statement already exists; `export const`
   just does not use it.

2. **An attribute-only component renders as nothing.** `reduceTags`
   (`starlight/discoverability.ts:296-322`) strips tags and keeps their children. That is
   right for a component whose content is in its slot, and wrong for one whose content is
   in its props. `<LinkCard title="Install" href="/..." >description</LinkCard>` reaches a
   reader as a bare description with no title and no link, so a section index becomes a
   list of orphan sentences. `dist/getting-started/index.md` lost all six of its
   navigation links this way, which is the one thing an index page exists to carry.

The parent gap-analysis issue already warns that a source-based MDX strip will misread
some authoring shapes. These are two concrete cases of that warning, and the second one
silently loses information rather than adding noise, which makes it the more serious of
the two.

**Second instance, found in P3 (#261).** Both defects reappear outside Getting started,
so neither is specific to one authoring style.

- `export const` still leaks: `dist/index.md` opens with the tail of the Home page's
  transcript array, ten lines of object literals, before the first sentence.
- `LinkCard` content still vanishes, and now with a measurable cost to the pages whose
  only job is navigation. `dist/modules/index.md` rendered `## Start here` and
  `## Module types` as empty headings, losing all ten cards, and `dist/index.md` lost
  nine. Beyond the title and href named above, the `description` prop is dropped too, so
  a card that says "17 modules: nsx-board-apollo2-evb, ..." reaches an agent as nothing
  at all.

**Status: shipped in `v0.1.0-alpha.16` as #143.** Both defects are fixed upstream:
multi-line `export` bodies, MDX comments and expressions are dropped from the
rendition, and a component carrying a literal `title` and `href` is emitted as
`- [title](href): children`. The local workaround
(`componentCards` in `astro-site/scripts/lib/render-agent-markdown.mjs`, plus the
relinking pass in `publish-agent-bundle.mjs` and the card-count assertion in
`check-discoverability-output.mjs`) is removed.

Two residues, neither blocking and both narrower than this draft. The fix reads
literal attributes only, so it does not recover a value built by an expression;
that is why the model-based composer for the generated CLI, config and API
renditions stays. And the description comes from the card's children, so a card
written with a `description=` prop still reaches an agent with its title and
link but no description: `dist/modules/index.md` shows exactly that. Worth a
follow-up draft rather than a reopen.

**What the pages do instead.** Transcript arrays moved into
`astro-site/src/data/transcripts/*.json` and are imported, because a single-line `import`
is stripped cleanly. The Getting started index dropped its `CardGrid` of `LinkCard`s for
an ordinary numbered list of Markdown links. Both are downgrades in authoring terms: the
data no longer sits next to the component that consumes it, and the index no longer uses
the package's cards.

**Why it matters.** The rendition is the artifact agents read, and #261 will build the
llms bundle from the same pass. A bundle that carries JavaScript literals as prose and
drops every card's link is worse than no bundle, because it reads as authoritative.

**Suggested shape.** For the first defect, reuse the existing multi-line handling: track
brace and bracket depth from the `export const` line and drop through the closing
`];` or `};`. For the second, give `reduceTags` a small map of prop-to-markdown rules for
the package's own link-bearing parts, so `LinkCard`, `Card` and `Button` emit
`[title](href)` plus their children. A generic fallback of "if a stripped tag had an
`href` and a `title`, emit a link" would cover most of it without a per-component table.

---

# Second pass: the landing page rebuild (issue #260)

Checked against `v0.1.0-alpha.15`, the version pinned when this pass ran. Same
rule as above: drafts only, nothing filed.

**Update to Draft 5, second defect.** Rebuilding the capability cards as `Card` +
`CardHeader` + `CardContent` instead of `LinkCard` turned out to fix half of it by
accident. `CardHeader` takes its title from the default slot, so the title survives
`reduceTags` and reaches the rendition; `LinkCard` takes `title` as a prop, so it does
not. The card's `href` is still lost either way. That makes the suggested fix narrower
than Draft 5 assumed: a prop-to-markdown rule is needed for `href`, but a part whose text
lives in a slot already renders correctly. Worth saying in the issue, because it means
"prefer the slot form" is a real authoring workaround available today.

**Superseded by #143 in `v0.1.0-alpha.16`, and inverted.** The rule that shipped emits a
link for any component carrying a literal `title` and `href`, so the prop form is now the
one that renders and the slot form is the one that does not: `CardHeader` carries the
`href` but states its title as children, so the capability grids on Home reach the
rendition as prose with no links. That is why Home still carries a "Read more:" row over
every `Card` + `CardHeader` grid and no longer needs one over its `LinkCard` grids.
Rewriting those cards to pass a literal `title` would retire the remaining rows; it is a
Home authoring change, not an upstream one.

---

## Draft 6: a card body cannot reach the primary ink

**Title:** `CardContent`: no way to set the body at `--helia-ink-primary`

**What happened.** The owner's review of the rebuilt landing page called the capability
card bodies "muddy". Measured on the built page (computed colors, alpha composited over
the first opaque ancestor):

| Element | Token | Light | Dark | Contrast |
| --- | --- | --- | --- | --- |
| `.helia-card-header__title` | `--helia-ink-primary` | `#17181c` | `#ffffff` | 17.7:1 / 19.0:1 |
| `.helia-card-content` | `--helia-ink-secondary` | `#353841` | `#c1c3c8` | 11.7:1 / 10.8:1 |

So this is not an accessibility defect: the body clears AAA in both themes. It is a
hierarchy the part fixes on the author's behalf. `recipes.css:823-824` sets
`.helia-card-content { color: var(--helia-ink-secondary) }`, and `CardContent`'s Props
(`astro/CardContent.astro`) are `padding` and `variant?: 'prose' | 'stats'` only. There is
no tone, emphasis or ink prop, so a card whose body is the point rather than a caption
cannot be authored at full contrast.

**What the page does instead.** Nothing. The cards ship at `--helia-ink-secondary`,
because the alternative is local CSS overriding a package class, which this site does not
do. The rebuild bought its legibility back with the icon disc, the eyebrow and the
whole-card link instead of with the text color.

**Why it matters.** Every product landing page is mostly cards, and the card body is where
the product's claims live. A part that always renders its body one step down from its
title is right for a navigation card and wrong for a feature card, and today they are the
same part.

**Suggested shape.** An `ink?: 'primary' | 'secondary'` (or `emphasis?: 'lead' | 'body'`)
on `CardContent`, defaulting to today's behavior. A `CardTone`-style union would be
heavier than needed; the ask is one step on an existing two-token scale.

---

## Draft 7: the Hero has no landing ground between `contrast` and nothing

**Title:** `Hero`: a third `variant` for a landing that should not be inked

**What happened.** `Hero.astro:30-33` documents the two values as a choice about what kind
of page it is: "`contrast` is the inked card a product landing opens on ... `plain` is the
same layout with no ground, for a page that is already a section of the site rather than
its front door." The owner's objection is that the first half now reads as a uniform: with
several HELIA products on the same frame, every one of them opens on the same dark card,
so the inked ground stops saying "this is a landing page" and starts saying nothing.

On the contrast ground the summary measures 12.6:1 and the eyebrow 8.45:1 against
`rgb(17,19,24)`, so nothing here fails 4.5:1 and no accessibility issue is being reported.
The summary is `--helia-ink-secondary`, which `recipes.css:2234-2238` redefines on the
contrast ground to `color-mix(in srgb, var(--helia-paper-white) 82%, transparent)`; at
18px against near-black that is what reads as dim beside a 100%-white headline, which is
the owner's "too dark".

**What the page does instead.** The landing uses `variant="plain"`, which the part's own
doc comment says is for a page that is *not* the front door. The page is the front door.
So the site is now using the value against its documented intent, and the next person to
read `Hero.astro` will reasonably "fix" it back.

**Why it matters.** This is a portfolio problem rather than a one-site problem. If the
inked hero is the house style for landings, then products need another way to not look
identical; if it is not, the doc comment should stop telling each of them to use it.

**Suggested shape.** Worth a question before an issue, like Draft 4. Either a third ground
(a tinted or paper landing ground that is still distinct from a body section), or keep two
values and rewrite the doc comment so `plain` is a legitimate landing choice rather than a
section-page one. The second costs nothing and would be enough here.

## Draft 8: a staged walkthrough part

**Title:** Walkthrough: a rail of stages over one AsciiTerminal, played one stage at a time

**What happened.** The neuralspotx landing page needed the install-to-running loop shown as stages rather than one long transcript. helia-ui has the ingredients (Surface, the chip recipe, AsciiTerminal, Reveal, ShowcaseCarousel) but no part that sequences terminals, so the site composed one locally: `astro-site/src/components/JourneyWalkthrough.astro`.

**Shape that worked.** `stages: { id, label, title, caption, lines }[]`, `dwell`, `typingSpeed`, `lineDelay`. A tablist rail of numbered chips, one terminal per stage stacked in a single grid cell so the card keeps the tallest stage's height, a live caption, Replay. Auto-advance starts on intersection, plays a stage through the terminal's own replay control, waits for `data-playing` to clear, dwells, then moves on; a rail click pauses autoplay; hover and focus pause; reduced motion shows the rail and the first stage with no animation. All stages render server-side for no-JS readers and the Markdown rendition.

**Proposal.** Adopt it as `astro/Walkthrough.astro` with that prop shape. **The two things this draft asked the package for both shipped in `v0.1.0-alpha.16` as #149:** every `AsciiTerminal` on a page is set up rather than only the first, and the element exposes `play()`, which waits for readiness and resolves when the run ends. The site no longer clicks a replay button or re-inserts a clone before each play; it calls `play()` and still hands off on `data-playing`, because the promise also settles for a run a later stage superseded. Nothing upstream now blocks adopting the part itself.

**Consumer context.** AmbiqAI/neuralspotx#260 hero. Related: #118 (output pacing), #149.
