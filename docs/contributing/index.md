# Contributing

This section is for engineers working on NSX itself rather than only consuming
it as an app developer.

Topics covered here:

- repo layout
- docs workflow
- release workflow
- agent guidance
- adding boards
- adding modules
- internal module coverage
- SDK provider model

## Contributor Expectations

When changing the platform:

1. keep user-facing docs aligned with the implementation
2. keep command examples consistent with current CLI help
3. validate the docs site builds successfully
4. keep board, module, and SDK metadata coherent

## Local git hooks

NSX uses pre-commit as the single lint gate. Install it once per clone:

```bash
uv tool install pre-commit
cd <nsx-repo>
pre-commit install
```

One `pre-commit install` covers both stages, because the config sets
`default_install_hook_types`.

The first run builds gitleaks, which downloads a Go toolchain and can take a
few minutes. Everything is cached under `~/.cache/pre-commit` after that.

| Stage | Runs | Why |
| --- | --- | --- |
| `pre-commit` | whitespace and file hygiene, gitleaks, ruff check, ruff format, `uv lock`, clang-format, deferred-work marker check | fast enough for every commit |
| `pre-push` | `ty` type check, plus the whitespace and large-file hooks, which declare pre-push upstream | whole-package check, not per-file |
| `manual` | the `pre-commit` row, with the staged gitleaks scan replaced by a whole-tree scan | CI only; the staged scan is blind in a fresh checkout |

Notes:

- CI runs `pre-commit run --all-files --hook-stage manual` on every pull
  request: the commit-stage hooks, with the whole-tree secret scan in place of
  the staged one. Skipping a hook locally only delays the failure.
- `SKIP=<hook-id> git commit` is the escape hatch when a hook is wrong. Say so
  in the pull request when you use it.
- Deferred work must be trackable: write `TODO(#123): ...` with the tracking
  issue, or `TODO(verify): ...` for a claim still waiting on a source of
  record. A bare `TODO`, `FIXME`, or `HACK` is rejected.
- The hooks never edit commit messages. What you write is what lands.
