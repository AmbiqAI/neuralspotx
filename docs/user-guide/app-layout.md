# App Layout

Generated NSX apps are designed to remain understandable as ordinary CMake
projects.

The app is the primary unit NSX creates and manages.

## Standard Layout

```text
<app-dir>/
  CMakeLists.txt
  nsx.yml
  src/
  cmake/nsx/
  modules/
  boards/
```

## What Each Part Does

- `CMakeLists.txt`: top-level app build entry
- `nsx.yml`: app metadata and module state
- `src/`: app-owned source code
- `cmake/nsx/`: copied NSX build helpers
- `modules/`: vendored module content
- `boards/`: vendored board definition for the selected target

## Why This Matters

The app does not depend on hidden build magic. The vendored structure makes it
clear:

- which modules are in use
- which board definition is active
- which CMake helpers are part of the generated app

In practice, this means the app is not just a generated output directory. It is
the user-facing application unit that NSX prepares for editing, building,
flashing, debugging, and sharing.
