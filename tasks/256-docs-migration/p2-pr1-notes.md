# P2 PR1 notes: Getting started (AmbiqAI/neuralspotx#260)

Branch `260-getting-started`, stacked on `259-module-catalog`, stacked on
`258-reference-generation`. Written against `nsx` 0.8.1 from the worktree checkout.

## 1. Source to page mapping, as applied

| New route | Sources it came from | What changed |
| --- | --- | --- |
| `/getting-started/` | `docs/getting-started/index.md` | Rewritten. Requirements table re-derived from `pyproject.toml` (`requires-python = ">=3.11"`), the generated app's `cmake_minimum_required(VERSION 3.24)` and the real `nsx doctor` check list. Lifecycle table added. Card grid replaces the MkDocs grid. Placeholder `:::note` pointing at #260 deleted. |
| `/getting-started/install/` | `docs/getting-started/install/index.md`, `macos.md`, `linux.md`, `windows.md` | Merged into one page with `CodeTabs` per step (host tools, Arm toolchain, J-Link). CLI install and the source-checkout note kept. Invented `nsx doctor` output replaced with a captured run. New paragraph stating `nsx --version` does not exist. |
| `/getting-started/install/macos/` | `docs/getting-started/install/macos.md` | Reduced to a deep-link page: a short all-in-one command block plus the armclang and ATfE setup, which is genuinely per-OS. Points back at the tabbed page. |
| `/getting-started/install/linux/` | `docs/getting-started/install/linux.md` | Same treatment, plus the package-manager alternative for the Arm toolchain. |
| `/getting-started/install/windows/` | `docs/getting-started/install/windows.md` | Same treatment, plus a `:::caution` saying the Windows steps have not been re-run on a Windows host. |
| `/getting-started/doctor/` | `docs/reference/doctor.md`, `docs/getting-started/install/index.md` | New page. Check table rebuilt from the captured output rather than the old list (which omitted the board-registry check). Failing run and `--json` shape added. Options deferred to the generated reference page. |
| `/getting-started/first-app/` | `docs/getting-started/first-app.md`, `docs/user-guide/create-app.md` | Split: only create-app stays here. Layout table rebuilt from a real run. `--template npu-tflm`, `--no-bootstrap`, `--soc` and `--force` documented. The five-command Mermaid diagram moved to the section overview as a table. |
| `/getting-started/configure-and-build/` | `docs/getting-started/first-app.md`, `docs/user-guide/build-flash-view.md`, `docs/reference/configure.md`, `docs/reference/build.md` | New page from the configure and build halves. Artifact list corrected. Option tables not repeated; the pages link to `/reference/cli/configure/` and `/reference/cli/build/`. |
| `/getting-started/flash-and-view/` | `docs/getting-started/first-app.md`, `docs/reference/flash.md`, `view.md`, `reset.md` | New page. Adds `nsx probes` and `nsx reset`, neither of which the old reference covered as part of the journey. Reset policy re-derived from `operations/_build.py`. |
| `/getting-started/next-steps/` | new | Links into Guides, Modules, Reference and the repository's `examples/`. |
| `/getting-started/migrate-from-neuralspot/` | `docs/contributing/migration-from-neuralspot.md` | Moved out of Contributing. Rewritten for length, module names linked to catalog pages where one exists, hardware-validation claims removed, and the link to the unpublished internal coverage page dropped. |

MkDocs sources under `docs/` are untouched; they stay live until #261.

## 2. What was validated, and how

Host: macOS 26.6.2, Apple silicon, Node 24, Arm GNU Toolchain 15.2.rel1, SEGGER J-Link
present, no board attached.

Every help text was captured with `uv run nsx <command> --help`: top level, `doctor`,
`create-app`, `configure`, `build`, `flash`, `reset`, `view`, `clean`, `probes`,
`commands`, `module`, `sbom`.

Runs behind the transcripts and claims:

| Run | Result |
| --- | --- |
| `nsx --version` | Fails, exit 2, `nsx: error: the following arguments are required: command`. Documented as not existing. |
| `nsx doctor` (full host) | Exit 0, all checks pass including armclang. |
| `nsx doctor` (host tools plus GCC plus J-Link only) | Exit 0. This is the transcript on the Install page. |
| `nsx doctor` (no Arm toolchain, no SWO viewer on `PATH`) | Exit 1. This is the failing transcript on the doctor page. |
| `nsx doctor --json` | Exit 0. Shape is `{ok, checks[], notes}`, each check `{label, ok, required, detail, hint}`. |
| `nsx create-app my_app --board apollo510_evb --no-bootstrap` | Exit 0. No `boards/`, empty `modules/`, `nsx.yml` gains `baseline: none`. |
| `nsx create-app my_app --board apollo510_evb` | Exit 0. Clones `nsx-ambiq-sdk` and `nsx-pmu-armv8m`, writes `boards/apollo510_evb/`. |
| `nsx create-app nb --no-bootstrap` (no `--board`) | Exit 0, `nsx.yml` records `apollo510_evb`, so the default is confirmed. |
| `nsx configure` | Exit 0, writes `nsx.lock`, `.nsx/` and `build/apollo510_evb/`. |
| `nsx build` | Exit 0, 24 Ninja steps, links `hello_ap510`, `hello_ap510.bin`, `hello_ap510.map`. |
| `nsx configure hello_world --board apollo510_evb` from the repo root | Exit 0, confirming the positional app argument resolves under `./examples`. |
| `nsx probes` | Exit 0, `No J-Link probes found.` with nothing attached. |
| `nsx board list` | Exit 0, 17 packaged boards. |

Transcript handling, so a reader knows what is verbatim:

- Absolute app paths are replaced with `/home/you/<app>`, matching the Home page's existing
  convention. Every other character of a transcript line is as captured.
- `nsx doctor` transcripts omit the indented path line under each check, because those are
  specific to the machine that ran it. Nothing else is removed.
- The `nsx configure` and `nsx build` transcripts collapse CMake's compiler-detection block
  and the middle of the Ninja log into a single `muted` line that says how many lines are
  missing.
- The size table's tabs are rendered as spaces so the columns line up in HTML.

## 3. Claims in the current docs that turned out to be wrong

1. **The `nsx doctor` sample output was invented.** `docs/getting-started/install/index.md`
   shows a two-column `Python ✓` layout. The real format is `[OK] <check>` with the
   resolved path indented beneath, `[FAIL] <check>` with a hint on failure, an `error:`
   header line when anything failed, and a closing `Next:` line. The old sample also misses
   the `Board registry` check and the `SEGGER J-Link runtime` check.
2. **`boards/` is real, but only after bootstrap.** The P2 content map flagged this as
   unresolved. A default `nsx create-app` does write `boards/<board>/`; `--no-bootstrap`
   does not. `docs/user-guide/app-layout.md` is therefore right about `boards/` and wrong
   only about when it appears.
3. **`nsx.lock` is written by `configure`, not by `create-app`.** A freshly created app has
   no lock file.
4. **The build does not produce a `.axf`.** `docs/getting-started/first-app.md` says
   "typically a `.bin` and `.axf` file". Under GCC you get an extension-less ELF, a `.bin`
   and a `.map`, plus a generated `jlink/` directory.
5. **The secure-reset SoC set is wider than "Apollo4 secure targets".**
   `docs/user-guide/build-flash-view.md` names Apollo4. `operations/_build.py` defines the
   attach-only set as `apollo3p`, `apollo4l`, `apollo4p` and `apollo510b`.
6. **`nsx reset` is not app-aware.** It requires `--device`, so the app-directory framing
   used for flash and view does not apply to it.
7. **`nsx probes` exists and was missing from the documentation entirely.**
8. **`nsx-gpio` and `nsx-psram` are not registry entries.** The migration guide names them.
   They are vendored inside the `nsx-ambiq-sdk` monorepo (`registry.lock.yaml`,
   `sdk_modules`), so they have no catalog page and must not be linked as if they did.
9. **Hardware-validation claims in the migration guide could not be sourced.** The
   "hardware-smoke validated" and "hardware validated" wording for `ns-ble` and `ns-tileio`
   has no source of record in this repository, so it was removed rather than repeated.

Two claims that did check out: the `MicroProfilerInterface` glue really does live only in
`examples/kws_infer`, and the npu-tflm template really does ship
`tools/tflite_to_header.py`.

## 4. Transcripts still owed, all needing hardware

Each is marked in the source with a `TODO(#260)` comment in
`astro-site/src/content/docs/getting-started/flash-and-view.mdx`. None of them is invented
in the meantime; the page says in a `:::caution` that its output is described rather than
captured.

1. `nsx probes` with a connected apollo510_evb, showing a probe serial.
2. `nsx flash` against a connected apollo510_evb, including the J-Link connect, program
   and verify lines.
3. `nsx view` against the same board, including the viewer's attach banner and the
   heartbeat lines.
4. `nsx reset --device AP510NFA-CBR` against the same board.

The device name `AP510NFA-CBR` is taken from the `-device` argument in the generated
`build/apollo510_evb/build.ninja`, so it is correct even without hardware.

## 5. Checks run

From `astro-site/`: `npm run build`, `npm run check` (0 errors, 0 warnings, 0 hints),
`npm run validate` (links, anchors, assets, reference and module completeness, SPDX,
American English). From the repo root: `uvx pre-commit@3.8.0 run --all-files --hook-stage
manual` and `uv run --group lint --group test ty check --error-on-warning src/neuralspotx
tests`.

Desktop screenshots of the Install and first-app pages were captured headless at 1440 px
against `astro preview`.
