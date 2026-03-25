# Agent Guidance

This page captures the architectural rules that future AI agents and automated
contributors should follow when modifying NSX.

The matching repo-local version lives in `AGENTS.md`. Keep this page and that
file aligned when the architecture changes.

## What NSX Is

`neuralspotx` is the tooling and workflow layer for NSX. It owns:

- workspace creation and synchronization
- app generation
- built-in board and module metadata
- configure/build/flash/view orchestration
- the public Python API used by future standalone tools

Changes should preserve the architecture first and the CLI surface second.

## Architectural Rules

### Keep NSX Workspace-First

NSX is workspace-first today.

- A workspace is the shared source-management environment.
- A workspace contains the `west` manifest and checked-out source repos.
- A workspace may contain multiple apps.
- Each app is the real build unit.

Standalone app support may come later, but the current product model assumes an
initialized workspace.

### Keep Apps Self-Contained

Apps vendor their own board and module content.

- Workspace repos are shared source-of-truth checkouts.
- App-local vendored content is the dependency snapshot the app actually builds
  with.

Do not replace this with implicit shared build-time dependency resolution.

### Use Registry-Driven Resolution

Built-in modules and SDK providers are defined through the packaged registry and
app-local overrides.

Primary sources:

- `src/neuralspotx/data/registry.lock.yaml`
- app-local `nsx.yml`

Normal behavior should prefer:

1. app-local vendored content
2. app-local registry overrides
3. built-in packaged registry plus workspace checkouts
4. explicit custom registrations

Do not reintroduce implicit sibling-repo fallback as a normal path.

### Prefer Library-First Changes

NSX should keep moving toward a shared library core.

Intended layering:

1. focused helper/data modules
2. shared operations layer
3. public Python API
4. CLI adapters

In practice:

- shared workflow logic belongs in `src/neuralspotx/operations.py`
- the public programmatic surface belongs in `src/neuralspotx/api.py`
- `src/neuralspotx/cli.py` should stay thin and delegate

When adding behavior, update the shared library path first and let both the API
and CLI consume it.

### Prefer Dataclasses For Owned Definitions

For structures NSX owns, prefer dataclasses over nested loose dictionaries.

This includes:

- request objects
- registry entries
- other internal schema-like definitions

Dataclasses make the code easier to reason about and reduce avoidable runtime
bugs.

### Prefer Jinja Templates For Generated Files

If NSX owns a generated file and it needs substitutions, use Jinja templates.

- templating helpers live in `src/neuralspotx/templating.py`
- generated app templates live under `src/neuralspotx/templates/`

Avoid growing long post-copy text replacement logic when a `.j2` template would
be clearer.

### Protect The Public Install Path

The public onboarding flow must keep working:

1. install with `pipx`
2. run `nsx doctor`
3. run `nsx init-workspace`
4. run `nsx create-app`
5. run `nsx configure`
6. run `nsx build`

A change that only works in a local developer checkout but breaks the public
install path is a regression.

## Coding Guidance

Prefer extraction over file growth.

Good helper modules include:

- config and path handling
- registry parsing and mutation
- tool discovery
- subprocess wrappers
- template rendering
- typed models

Also keep the user experience clean:

- friendly failure messages for normal users
- verbose detail only when explicitly requested

## Testing Guidance

Prefer fast, CI-safe tests by default.

- API dispatch tests should be mock-based and fast.
- E2E tests should prefer local no-network flows.
- Avoid tests that download public module repos unless the test is explicitly
  for that path.

When changes are broad, validate:

```bash
uv run --group lint ruff check .
uv run --group test pytest -q
uv run --group docs zensical build
```

## Workflow Guidance

Use the standard repo workflow:

- work on feature branches
- open PRs
- squash merge
- use Conventional Commit titles so Release Please can reason about releases

Examples:

- `feat: add board listing command`
- `fix: improve segger connection errors`
- `docs: clarify pipx install workflow`
- `refactor: extract module registry helpers`

## When The Architecture Changes

If a PR changes one of the rules above:

1. update the implementation
2. update the contributor docs
3. update `AGENTS.md`
4. make the PR description explicit about the design change
