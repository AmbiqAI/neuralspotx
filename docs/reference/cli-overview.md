# CLI Overview

`nsx` is the primary interface for the NSX app lifecycle.

Current top-level commands:

- `init-workspace`
- `create-app`
- `new`
- `sync`
- `doctor`
- `configure`
- `build`
- `flash`
- `view`
- `clean`
- `module`

## Typical Lifecycle

1. initialize a workspace
2. run `doctor` if the local toolchain or SEGGER environment looks suspect
3. create an app
4. configure the app
5. build the app
6. flash and view output
7. add or remove modules as needed

Use the task-oriented pages in **User Guide** when you want workflow help.
Use this section when you want exact command syntax.
