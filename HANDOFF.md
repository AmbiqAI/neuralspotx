# NSX documentation polish

## Goal and scope
Polish NSX docs under AmbiqAI/neuralspotx#256, then open a PR for review before moving to profiler. No merge or deployment authorized in this pass. Use CLI and headless browsers only; never control desktop windows or the user's browser tabs.

## State
Existing worktree neuralspotx-alpha18, branch 256-helia-ui-alpha-18. Preserved unpublished commit3396ddf. Based on main6afb7d2; fetched main and confirmed no divergence. PR https://github.com/AmbiqAI/neuralspotx/pull/275 is open and attached. Remote head verified as 1990ca25d6ae6c3e3789147ecad344a38f1fd8cb; CI running.

## Changes
- Shared helia-ui alpha.20, aligned header/footer and task-based navigation.
- NSX-branded hero with application/module/hardware stack, four capability buckets and Apollo3/4/5 families. Accessible carousel with reduced motion and mobile layout.
- Basic animated setup/check/create/build/flash/view walkthrough before dedicated module search/add/build section. Pause/Resume, Replay and manual stage selection.
- Spacing between featured examples and More examples button; trimmed redundant landing content.
- Filterable module catalog with search, capability/type/target facets and expandable cards. Libraries and services replaces runtime presentation; platform navigation reorganized with stable URLs.
- Onboarding transcripts abbreviated and illustrative hardware output labeled. Removed distracting Git warning.
- Installation OS selections synchronize across three terminal groups without moving keyboard focus.
- Guide hubs, ordering, section names and source-checked claims polished. Source/API URLs retained.
- Markdown/LLM export includes walkthrough and module commands; output guards check semantic parity.

## Reviews and verification
Two independent content/UI reviews completed. Fixed all four findings: missing terminal exports, portability overclaim, hidden-page autoplay stall and stale focus/hover pause state. Added explicit controls and lifecycle cleanup.
Final build, full validate and Astro check passed (0 diagnostics). Ten headless Playwright tests passed: hero responsive layout/selection/reduced motion, catalog filters, walkthrough looping/pause/visibility and OS-tab sync/focus. Rendered screenshots inspected at /tmp/nsx-final-workflow.png and /tmp/nsx-final-examples.png. Earlier pass ran65 Python documentation tests and responsive/theme checks. No hardware or Windows execution; no complete new audit of untouched APIs.

## Next
Review CI and PR #275 before merge. No agent-generated label exists in this repository. User preview remains at http://127.0.0.1:8760/neuralspotx/. Do not stop it. Logs: /tmp/nsx-build.log, /tmp/nsx-validate.log, /tmp/nsx-check.log, /tmp/nsx-hero-tests.log. Use npm run test:hero from astro-site after build; test preview uses8761 and --ignore-lock.

## Latest polish
Removed hover lift from the four Home documentation cards and replaced the section-count introduction with task-oriented copy. Build and full validation passed; headless hover checks confirmed all four cards retain position with no transform or shadow. Render inspected at /tmp/nsx-doc-cards-final.png.
Your project band now uses the default background between muted Modules and HELIA sections. Build passed and rendered screenshot inspected at /tmp/nsx-project-background.png.
Hero active progress dot toggles pause/resume, preserving elapsed time and freezing CSS slide animation. Slide labels select/reset without clearing pause. Separate labeled keyboard buttons retain compact presentation. Build/check and all11 headless tests pass, including paused progress, animation state, label switching while paused, and keyboard resume.
Compacted hero carousel to431px at1032px viewport: SDK uses three layers, Modules four capability tiles without extra frame/application block, Targets family tiles and compiler line. Shortened captions and diagram space; all slides retain equal height. Build, full validation and11 interaction tests pass. Inspected /tmp/nsx-compact-{SDK,Modules,Targets}.png.
Walkthrough pacing now45ms per command character,650ms between lines and5.5s completed-output dwell. SVG outline traces the active tab across the full step. Active-tab click pauses/resumes the shared typing/progress timeline, other tabs preserve pause. Reduced motion remains static. Build, check, validation and12 interaction tests pass; /tmp/nsx-outline-progress.png inspected.
Targets visual restored to two labeled rows: outlined silicon-family boxes and filled GCC/ATfE/ACFE boxes. Compact431px carousel height retained at1032px. Screenshot /tmp/nsx-target-toolchains.png inspected; build and12 interaction tests pass.
