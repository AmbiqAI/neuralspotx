# helia-ui gaps found during P2 PR1, Getting started (issue #260)

Drafts only. Nothing below has been filed; Adam files or discards each one.
Checked against `v0.1.0-alpha.14`, the version pinned in
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
