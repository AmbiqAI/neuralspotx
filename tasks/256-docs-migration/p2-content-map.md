# P2 content map (AmbiqAI/neuralspotx#260)

Prepared 2026-09-20 against `main` at 518b2b4 and `258-reference-generation` at c431d40.
Old routes assume MkDocs `use_directory_urls` under the `/neuralspotx/` base. Facts below
come from the repo and from real CLI runs; anything unverified is marked `verify`.

## 1. Fate of all 67 pages

| Old route | Source file | Fate |
| --- | --- | --- |
| `/` | docs/index.md | rewrite -> `/` (Home, already scaffolded in #262) |
| `/getting-started/` | getting-started/index.md | rewrite -> `/getting-started/` |
| `/getting-started/install/` | install/index.md | rewrite with OS tabs -> `/getting-started/install/` |
| `/getting-started/install/macos/` | install/macos.md | keep -> `/getting-started/install/macos/` |
| `/getting-started/install/linux/` | install/linux.md | keep -> `/getting-started/install/linux/` |
| `/getting-started/install/windows/` | install/windows.md | keep -> `/getting-started/install/windows/` |
| `/getting-started/first-app/` | getting-started/first-app.md | split -> `/getting-started/first-app/`, `/getting-started/configure-and-build/`, `/getting-started/flash-and-view/` |
| `/user-guide/app-model/` | user-guide/app-model.md | keep -> `/guides/apps/app-model/` |
| `/user-guide/create-app/` | user-guide/create-app.md | merged into `/guides/apps/app-model/` (overlaps Getting started) |
| `/user-guide/app-layout/` | user-guide/app-layout.md | rewrite -> `/guides/apps/app-layout/` (layout is stale, see risks) |
| `/user-guide/modules/` | user-guide/modules.md | rewrite for users -> `/guides/modules/using-modules/` |
| `/user-guide/module-catalog/` | user-guide/module-catalog.md | dropped (2757 words, hand-maintained, already drifted; superseded by generated `/modules/`) |
| `/user-guide/custom-modules/` | user-guide/custom-modules.md | keep, tighten -> `/guides/modules/custom-modules/` |
| `/user-guide/lock-and-sync/` | user-guide/lock-and-sync.md | keep, tighten -> `/guides/modules/lock-and-sync/` |
| `/user-guide/python-api/` | user-guide/python-api.md | rewrite -> `/guides/python-api/` |
| `/user-guide/build-flash-view/` | user-guide/build-flash-view.md | tighten -> `/guides/apps/build-flash-view/` |
| `/user-guide/boards-and-targets/` | user-guide/boards-and-targets.md | tighten -> `/guides/apps/boards-and-targets/` |
| `/user-guide/sdk-provider-selection/` | user-guide/sdk-provider-selection.md | merge with architecture/sdk-provider-model.md -> `/guides/modules/sdk-providers/` |
| `/user-guide/system-init/` | user-guide/system-init.md | keep -> `/guides/system/system-init/` |
| `/user-guide/memory-placement/` | user-guide/memory-placement.md | keep -> `/guides/system/memory-placement/` |
| `/user-guide/startup-and-linker/` | user-guide/startup-and-linker.md | keep -> `/guides/system/startup-and-linker/` |
| `/user-guide/troubleshooting/` | user-guide/troubleshooting.md | rewrite -> `/guides/apps/troubleshooting/` |
| `/reference/cli-overview/` | reference/cli-overview.md | merged into generated `/reference/cli/` |
| `/reference/commands/` | reference/commands.md | merged into `/reference/cli/commands/` |
| `/reference/create-app/` | reference/create-app.md | merged into `/reference/cli/create-app/` |
| `/reference/doctor/` | reference/doctor.md | merged into `/reference/cli/doctor/` |
| `/reference/configure/` | reference/configure.md | merged into `/reference/cli/configure/` |
| `/reference/build/` | reference/build.md | merged into `/reference/cli/build/` |
| `/reference/flash/` | reference/flash.md | merged into `/reference/cli/flash/` |
| `/reference/reset/` | reference/reset.md | merged into `/reference/cli/reset/` |
| `/reference/view/` | reference/view.md | merged into `/reference/cli/view/` |
| `/reference/clean/` | reference/clean.md | merged into `/reference/cli/clean/` |
| `/reference/module/` | reference/module.md | merged into `/reference/cli/module/` plus subcommand pages |
| `/reference/sbom/` | reference/sbom.md | merged into `/reference/cli/sbom/` |
| `/reference/public-api/` | reference/public-api.md | merged into generated `/reference/api/` |
| `/architecture/` | architecture/overview.md | rewrite -> `/guides/concepts/` |
| `/architecture/app-generation-flow/` | app-generation-flow.md | rewrite for users -> `/guides/concepts/app-generation-flow/` |
| `/architecture/dependency-model/` | dependency-model.md | rewrite for users -> `/guides/concepts/dependency-model/` |
| `/architecture/module-model/` | module-model.md | rewrite for users -> `/guides/concepts/module-model/` |
| `/architecture/metadata-model/` | metadata-model.md | tighten, link to generated config reference -> `/guides/concepts/metadata-model/` |
| `/architecture/multi-target-portability/` | multi-target-portability.md | rewrite for users -> `/guides/concepts/multi-target/` |
| `/architecture/sdk-provider-model/` | sdk-provider-model.md | merged into `/guides/modules/sdk-providers/` |
| `/architecture/toolchain-support/` | toolchain-support.md | keep -> `/guides/system/toolchains/` |
| `/architecture/design-decisions/` | design-decisions.md | maintainers (unpublished) |
| `/architecture/sdk-upstream-plan/` | sdk-upstream-plan.md | maintainers (unpublished) |
| `/architecture/board-coverage/` | board-coverage.md | maintainers (unpublished); user-facing board facts come from generated `/modules/boards/` |
| `/examples/` | examples/index.md | rewrite as filterable table -> `/guides/examples/` |
| `/examples/hello_world/` .. `/examples/usb_rpc/` (10 stubs: hello_world, freertos_blinky, coremark, power_benchmark, pmu_profiling, kws_infer, ble_webble, audio_capture, usb_serial, usb_rpc) | examples/*.md | keep one page each -> `/guides/examples/<name>/`, README include replaced by an Astro import of `examples/<name>/README.md` (`verify` that the import works with the Astro content collection) |
| `/contributing/` | contributing/index.md | split: user-facing part -> `/guides/contribute/`, mechanics -> root CONTRIBUTING.md |
| `/contributing/agent-guidance/` | agent-guidance.md | keep -> `/guides/contribute/agent-guidance/` |
| `/contributing/adding-boards/` | adding-boards.md | keep -> `/guides/contribute/adding-a-board/` |
| `/contributing/adding-modules/` | adding-modules.md | keep -> `/guides/contribute/adding-a-module/` |
| `/contributing/docs-workflow/` | docs-workflow.md | keep -> `/guides/contribute/docs-workflow/`, rewritten for Astro (open question 4) |
| `/contributing/migration-from-neuralspot/` | migration-from-neuralspot.md | move -> `/getting-started/migrate-from-neuralspot/` |
| `/contributing/releases/` | releases.md | split: versioning policy -> `/reference/releases/`, mechanics -> maintainers |
| `/contributing/repo-layout/` | repo-layout.md | maintainers (unpublished) |
| `/contributing/module-coverage/` | module-coverage.md | maintainers (unpublished) |
| (no route, orphan) | contributing/sdk-providers.md | dropped; its one useful fact (current SDK bundle) moves to `/guides/modules/sdk-providers/` sourced from the registry lock |

Counts: 67 files accounted for. Published new routes: 10 Getting started, 24 Guides,
generated Modules and Reference, 6 maintainers files, 2 dropped.

## 2. Getting started journey

Each page uses `AsciiTerminal` for its "what you should see" block. Every transcript must be
captured from a real run, not written by hand.

1. `/getting-started/` Overview and requirements. Sources: getting-started/index.md.
   Transcript: none. Validate: the supported host OS list and the Python/uv minimum
   against pyproject `requires-python` (`verify`).
2. `/getting-started/install/` Install, OS tabs on one page. Sources: install/index.md,
   macos.md, linux.md, windows.md. `CodeTabs` for per-OS commands. Transcript: `nsx doctor`
   as the post-install check. `nsx --version` does not exist: the top-level parser accepts
   only `-h`, `-v` (verbose) and `-q`, and `nsx --version` fails with "the following
   arguments are required: command". Validate: Homebrew cask/formula names, apt package
   names and the Windows install path against a real run on each OS.
3. `/getting-started/install/{macos,linux,windows}/` deep-link pages, unchanged content,
   each linking back to the tabbed page.
4. `/getting-started/doctor/`. Sources: reference/doctor.md, install pages.
   Transcript: `nsx doctor` on a machine with the toolchain present, and one failing run
   showing a missing tool. Validate: doctor's only flag is `--json`; the check names and
   pass/fail wording must come from the captured output, not from the old page.
5. `/getting-started/first-app/`. Sources: getting-started/first-app.md, user-guide/create-app.md.
   Transcript: `nsx create-app my_app --board apollo510_evb` plus a `tree` of the result.
   Validate: flags are `--board`, `--soc`, `--force`, `--no-bootstrap`, `--template
   {default,npu-tflm}`. The `npu-tflm` template is undocumented today and should be
   mentioned here. Generated layout from a real run (`--no-bootstrap`, apollo510_evb) is
   `CMakeLists.txt`, `README.md`, `.gitignore`, `nsx.yml`, `src/main.c`, `cmake/nsx/`,
   `cmake/presets/`, `modules/`. There is no `boards/` directory, which contradicts
   user-guide/app-layout.md; re-run with bootstrap to confirm (`verify`).
6. `/getting-started/configure-and-build/`. Sources: first-app.md, user-guide/build-flash-view.md,
   reference/configure.md, reference/build.md. Transcripts: `nsx configure` and `nsx build`
   including the final artifact lines. Validate: the positional `app` argument resolves under
   `./` and `./examples`; `--toolchain` accepts gcc, armclang, atfe; `--frozen` and
   `--timeout` exist on both; `--jobs`, `--target`, `--update` are build-only.
7. `/getting-started/flash-and-view/`. Sources: first-app.md, reference/flash.md, view.md,
   reset.md. Transcripts: `nsx probes`, `nsx flash`, `nsx view` with live SWO lines.
   Validate: `nsx probes` exists and is absent from the old reference; `--probe-serial`
   always forces a reconfigure (stated in flash/view help); view has `--duration`,
   `--capture`, `--reset-on-open/--no-reset-on-open`, `--reset-delay-ms`.
   Hardware is required for these three transcripts; schedule a runner session on a
   connected apollo510_evb.
8. `/getting-started/next-steps/`. New page. Links into Guides, Modules, Examples, Reference.
   No transcript.
9. `/getting-started/migrate-from-neuralspot/`. Source: contributing/migration-from-neuralspot.md.
   Transcript: none. Every command and API name in it needs a pass against the current CLI
   (see risks).

## 3. Guides sidebar

**Apps**: app-model (keep), app-layout (rewrite, layout is wrong), create-app merged into
app-model, build-flash-view (tighten, point at generated CLI pages instead of repeating
options), boards-and-targets (tighten, link generated board matrix), troubleshooting
(rewrite around real error strings).

**Modules in your app**: using-modules (rewrite from user-guide/modules.md), custom-modules
(keep, tighten, drop duplicated option tables), lock-and-sync (keep, tighten), sdk-providers
(merge user-guide/sdk-provider-selection.md with architecture/sdk-provider-model.md and the
orphan contributing/sdk-providers.md). Source versus prebuilt integration gets one section
only if the code supports it (`verify`).

**System**: system-init (keep), memory-placement (keep), startup-and-linker (keep),
toolchains (keep, from architecture/toolchain-support.md).

**Concepts**: index (rewrite from architecture/overview.md), app-generation-flow,
dependency-model, module-model, metadata-model, multi-target. All rewritten for users, with
schema tables deleted in favour of the generated config reference.
Architecture pages that read as maintainer material and should go to `docs/maintainers/`
instead: design-decisions.md, sdk-upstream-plan.md, board-coverage.md.

**Python API**: one guide page (rewrite of user-guide/python-api.md) pointing at generated
`/reference/api/`.

**Examples**: overview with a filterable table built from the stubs' front matter (tier,
capabilities, status, boards_tested) plus ten per-example pages.

**Contribute** (collapsed): agent-guidance, adding-a-board, adding-a-module, docs-workflow.

## 4. Maintainers set

Move to `docs/maintainers/`, excluded from the Astro build and producing no route:
`design-decisions.md`, `sdk-upstream-plan.md`, `board-coverage.md`, `repo-layout.md`,
`module-coverage.md`, `releases.md` (mechanics only; the versioning policy section moves to
`/reference/releases/`).

Root `CONTRIBUTING.md`, short: how to file an issue, the no-code-without-an-issue rule,
dev setup with uv, how to run tests and lint, commit and PR conventions including
release-please, where the docs live and how to build them, a pointer to
`docs/maintainers/` for release mechanics and internal coverage, and the security contact.
One page, no duplication of `docs/maintainers/` content.

## 5. PR split

**PR 1: Getting started.** The ten routes in section 2, redirects deferred to #261.
Acceptance: every command shown appears in `nsx <cmd> --help` with the same flag spelling;
every `AsciiTerminal` transcript is a captured run and the PR body names the host and board;
the generated app layout in the docs matches a fresh `nsx create-app`; Windows steps
executed on a Windows host; no internal broken links; desktop and mobile, light and dark
screenshots attached.

**PR 2: Guides and Concepts.** Apps, Modules in your app, System, Concepts, Python API,
Contribute groups, plus the maintainer-docs move and the root CONTRIBUTING.md.
Acceptance: `docs/maintainers/` produces no route in `dist`; no Guides page repeats an
option table that the generated reference already carries; every compatibility statement
says declared, never validated; the orphan `contributing/sdk-providers.md` is deleted and
its content relocated; link and anchor check clean.

**PR 3: Modules prose and Examples.** Prose around #259's generated pages, the "how
compatibility is declared" note, the Examples overview with the filterable table, and the
ten example pages. Acceptance: the example table's rows match the front matter in the
example stubs with no hand-entered values; the filter works with JavaScript disabled by
falling back to the full static table; each example page renders the current
`examples/<name>/README.md`; unsupported or experimental capabilities are labelled.

## 6. Risks and open questions

1. `user-guide/app-layout.md` documents a `boards/` directory that a real `create-app` run
   did not produce. Confirm what a bootstrapped app contains before PR 1 quotes a layout.
2. `contributing/sdk-providers.md` states that all provider and wrapper modules resolve to
   `v5.2.24`. The registry lock now carries both `v5.2.24` (26 pins) and `v5.2.25` (5 pins).
   Any SDK revision in prose should be generated or dropped.
3. `user-guide/module-catalog.md` claims 52 modules over 98 rows against 50 registry
   entries. Dropping it in favour of the generated catalog is the proposal; owner sign-off
   needed because it is the single largest page.
4. Plan section 2 lists `docs-workflow` both under Guides Contribute and under the
   unpublished set. Proposal here keeps it public and rewritten for Astro. Owner to confirm.
5. The neuralSPOT migration guide (1381 words) has never been validated against the current
   CLI. It needs a full command and API pass, or a clear "written against NSX 0.x" note.
6. Windows install steps cannot be validated from this host. PR 1 needs a Windows runner or
   an owner-run check.
7. Board and SoC claims (17 packaged boards, tiers, toolchains) must come from
   `src/neuralspotx/boards/*/board.yaml` through the #259 generator, not from prose.
8. Flash, view and probes transcripts need attached hardware. If no board is available in
   time, PR 1 should ship those pages with the transcript blocks marked as pending rather
   than with invented output.
9. Examples README inclusion moves from a MkDocs snippet to an Astro import. Confirm the
   import path works from outside `astro-site/` before PR 3.
