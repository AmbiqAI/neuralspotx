# NSX documentation polish

## Goal
Complete documentation polish under AmbiqAI/neuralspotx#256 and prepare PR #275 for merge. No merge or deployment authorized in this pass. Use CLI and headless browsers only; never control desktop windows or existing browser tabs.

## State
Worktree: /Users/adam.page/Ambiq/neuralspotx/neuralspotx-alpha18.
Branch: 256-helia-ui-alpha-18. PR: https://github.com/AmbiqAI/neuralspotx/pull/275.
The initial commit 3396ddf is preserved. Base was main commit 6afb7d2. Review fixes through da85885 were pushed; remaining Copilot fixes passed local validation and are ready to push.

## Final implementation
- helia-ui alpha.20, common header/footer, and task-oriented guide navigation with stable URLs.
- Compact NSX hero with SDK stack, module capability tiles, silicon families and toolchain tiles. Equal-width stack layers, centered AmbiqSuite foundation and consistent teal palette.
- Hero active dot pauses/resumes; labels select slides without clearing pause. Paused selection displays the complete slide. Reduced motion stays static.
- Walkthrough tabs trace progress around their outlines. Active-tab clicks pause/resume typing; selecting another tab preserves pause and displays the complete transcript. Captions sit below tabs and above the terminal. No separate Replay or Pause/Resume buttons.
- Module catalog has search, facets and expandable cards. Installation OS tabs synchronize without moving keyboard focus.
- Installation and Home terminal content is composed from shared data into Markdown/LLM exports, with completeness guards.
- Hardware output is explicitly illustrative. No copy control on the illustrative probe/flash transcripts.
- Version lookup uses uv tool list or pipx list, not an unsupported top-level CLI option.

## Review disposition
Two independent content/UI reviews completed; all four findings were fixed and independently rechecked. Copilot's export, version lookup, paused-selection, replay and handoff findings are addressed. Browser interaction checks are now wired into the docs workflow after the build/validation, with the locked Playwright Chromium installation.
The visible footer commit stamp remains removed per the user's explicit request; source provenance remains in build-info.json. This supersedes the earlier issue's visible-stamp requirement.

## Validation and limits
Build, full documentation validation, Astro check (zero diagnostics) and 12 headless interaction tests passed after the independent-review fixes. A final pass checked six pages at three widths in both themes: 36 combinations, no overflow or page errors. Earlier work ran 65 Python documentation tests. No new hardware execution or Windows installation validation. Do not equate CI success with deployment.

## Next
Push the remaining Copilot cleanup, verify remote head and inspect CI before merge. Local build, full validation, all 12 interaction tests and workflow YAML parsing passed; the rendered illustrative terminals have no copy controls. Keep the user's preview at http://127.0.0.1:8760/neuralspotx/ running. Browser tests serve the built site on port 8761 with --ignore-lock. Logs: /tmp/nsx-build.log, /tmp/nsx-check.log, /tmp/nsx-validate.log and /tmp/nsx-hero-tests.log.
