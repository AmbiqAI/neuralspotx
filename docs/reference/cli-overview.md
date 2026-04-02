# CLI Overview

`nsx` is the primary interface for the NSX app lifecycle.

Current top-level commands:

- `commands`
- `create-app`
- `new`
- `doctor`
- `configure`
- `build`
- `flash`
- `view`
- `clean`
- `module`

## Typical Lifecycle

1. run `doctor` if the local toolchain or SEGGER environment looks suspect
2. create an app
3. configure the app
4. build the app
5. flash and view output
6. add or remove modules as needed

## Agent-Friendly Discovery

For LLM and agent workflows, prefer the CLI discovery surfaces over scraping
table output or general help text:

- `nsx commands --json` for the command tree, arguments, and workflow hints
- `nsx module list --json` for catalog discovery
- `nsx module describe <module> --json` for per-module metadata

Use the task-oriented pages in **User Guide** when you want workflow help.
Use this section when you want exact command syntax.
