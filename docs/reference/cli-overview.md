# CLI Overview

`nsx` is the primary interface for the NSX app lifecycle.

Current top-level commands:

- `add`
- `board`
- `build`
- `cache`
- `clean`
- `commands`
- `configure`
- `create-app`
- `doctor`
- `flash`
- `list-modules`
- `lock`
- `module`
- `new`
- `outdated`
- `probes`
- `reset`
- `sbom`
- `sync`
- `update`
- `view`

`add`, `list-modules`, and `new` are convenience aliases. Run
`nsx commands` for the categorized command graph and workflow hints.

## Typical Lifecycle

1. run `doctor` if the local toolchain or SEGGER environment looks suspect
2. create an app
3. configure the app
4. build the app
5. flash and view output
6. add or remove modules as needed

## App Directory Resolution

Most NSX commands operate on an app directory containing `nsx.yml`.

- If you run a command from the app root, you can usually omit `--app-dir`.
- If you run a command from a subdirectory inside the app, NSX walks upward
  until it finds the nearest `nsx.yml`.
- The upward search stops at the filesystem root or a Git repository boundary.
- Use `--app-dir` when you want to target a different app explicitly.

## Agent-Friendly Discovery

For LLM and agent workflows, prefer the CLI discovery surfaces over scraping
table output or general help text:

- `nsx commands --json` for the command tree, arguments, and workflow hints
- `nsx module list --registry-only --json` for catalog discovery
- `nsx module describe <module> --json` for per-module metadata

Use the task-oriented pages in **User Guide** when you want workflow help.
Use this section when you want exact command syntax.

The JSON command graph is the authoritative machine-readable syntax source.
Reference pages summarize common options, so automation should consume
`nsx commands --json` instead of copying usage text from documentation.
