# NSX Agent Guide

This file is for AI agents and automated contributors working in
`neuralspotx`. It captures the architectural choices and repo workflows that
should stay stable unless there is a deliberate design change.

## Purpose

`neuralspotx` is the tooling, templating, metadata, and workflow layer for NSX.
It is not just a CLI wrapper. It is the source of truth for:

- workspace creation and synchronization
- app generation
- built-in board and module registry metadata
- configure/build/flash/view workflows
- the public Python API used by future standalone tools

When changing this repo, preserve the architecture first and the CLI surface
second.

## Current Architectural Choices

### Workspace-First Model

NSX is workspace-first today.

- A workspace is the shared source-management environment.
- A workspace contains a `west` manifest and checked-out source repos.
- A workspace can contain multiple apps.
- An app is the build unit.
- Each app vendors its own modules and board content locally.

Do not silently switch the product model to standalone-first. Standalone app
support may come later, but the current design assumes an initialized
workspace.

### App-Local Vendoring

Generated apps vendor their dependencies.

- Workspace repos are shared source-of-truth checkouts.
- App-local `modules/` content is the dependency snapshot the app actually
  builds with.
- App-local board content should remain explicit and understandable.

Do not replace vendoring with implicit shared build-time dependency resolution.

### Registry-Driven Built-Ins

Built-in NSX modules and SDK providers are resolved through packaged registry
metadata, not by scanning sibling folders.

Primary sources:

- `src/neuralspotx/data/registry.lock.yaml`
- app-local `nsx.yml` overrides

Normal resolution order should remain:

1. app-local vendored content
2. app-local registry overrides
3. built-in packaged registry + workspace checkouts
4. explicit local/custom registrations

Do not reintroduce implicit sibling repo fallback as a default behavior.

### Library-First Direction

The intended layering is:

1. focused helper/data modules
2. shared operations layer
3. Python API
4. CLI adapters

Today that means:

- shared workflow logic belongs in `src/neuralspotx/operations.py`
- helper concerns belong in small focused modules such as:
  - `models.py`
  - `project_config.py`
  - `module_registry.py`
  - `templating.py`
  - `tooling.py`
  - `subprocess_utils.py`
- `api.py` should expose a clean, typed public programmatic surface
- `cli.py` should stay thin and delegate

When adding behavior, prefer changing the shared library path first and then
have both the API and CLI consume it.

### Typed Internal Models

For definitions NSX owns, prefer dataclasses over ad hoc dictionaries.

Use dataclasses for:

- app/workspace request types
- registry project/module entries
- other internal schemas we control

Avoid spreading nested `.get(...)` chains when a typed model is practical.

### Jinja-Based Templating

Generated app content should use Jinja templates where NSX owns the files.

- Template rendering lives in `src/neuralspotx/templating.py`
- App templates live under `src/neuralspotx/templates/`
- Prefer `.j2` templates for files with app/board/SoC substitutions

Do not add long post-copy string-rewrite logic when templating is a better fit.

### Public Install Path

The public onboarding path matters and must remain healthy.

Supported external flow:

1. install `neuralspotx` with `pipx`
2. run `nsx doctor`
3. run `nsx init-workspace`
4. run `nsx create-app`
5. run `nsx configure`
6. run `nsx build`

Changes that only work in a local developer checkout but break the public
install path are regressions.

## Working Rules

### Prefer Focused Modules

If `cli.py`, `operations.py`, or another file starts accumulating multiple
distinct responsibilities, extract a focused helper module instead of growing
the file indefinitely.

Good candidates for extraction:

- config and path handling
- registry parsing and mutation
- subprocess wrappers
- tool discovery
- template rendering
- typed models

### Keep Docs Aligned

When behavior changes, update docs in the same change when practical.

At minimum, check:

- `README.md`
- user-facing docs under `docs/`
- contributor docs when the architecture changes
- this `AGENTS.md` file if the architectural rule itself changed

### Prefer No-Network Tests by Default

Fast local and CI-safe tests are preferred.

- API dispatch tests should be mock-based and fast.
- E2E tests should prefer no-network local flows.
- Avoid tests that download public module repos unless the test is explicitly
  for that path and justified.

### Preserve Friendly Failure Paths

User-facing operations like flash/view/doctor should fail with actionable
messages, not raw tracebacks, unless verbose mode is explicitly requested.

### Release Discipline

`neuralspotx` uses PR-first workflow and Release Please.

- Work on feature branches.
- Open PRs instead of pushing feature work directly to `main`.
- Use squash merges.
- Use Conventional Commit titles for squash merges so Release Please can reason
  about releases.

Examples:

- `feat: add board listing command`
- `fix: improve segger connection errors`
- `docs: clarify pipx install workflow`
- `refactor: extract module registry helpers`

## Validation Expectations

Before sending or merging changes, run the relevant checks from repo root:

```bash
uv run --group lint ruff check .
uv run --group test pytest -q
uv run --group docs zensical build
```

Run narrower commands only when appropriate, but prefer not to skip the full
set for cross-cutting changes.

## High-Risk Regressions To Avoid

Avoid introducing these without an explicit design decision:

- implicit sibling-repo dependency resolution
- CLI-only behavior that bypasses the shared operations/API layer
- new internal schema represented as loose nested dictionaries when dataclasses
  are practical
- app generation via brittle text replacement instead of templating
- tests that require private network access for normal CI
- docs that describe a flow different from the implemented product behavior

## If You Need To Change The Architecture

When changing a major architectural choice:

1. update the implementation
2. update the contributor docs
3. update this file
4. keep the PR description explicit about the design change and why it is worth
   it
