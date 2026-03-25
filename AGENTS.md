# AGENTS

This repo uses a PR-first workflow.

## Branching

- Do not push feature work directly to `main`.
- Create a feature branch for each change.
- Open a pull request and merge through GitHub.

## Merge Style

- Prefer squash merges for feature branches.
- The squash commit title must use Conventional Commits so Release Please can detect releasable changes.

Examples:

- `feat: add board list command`
- `fix: restore uv run in source checkout README flow`
- `docs: clarify pipx install path`
- `test: add workspace bootstrap regression coverage`
- `ci: guard Pages deploys to default branch`
- `refactor: move app workflows into operations layer`

## Release Please

Release Please runs on pushes to `main` and only creates or updates a release PR when it sees releasable Conventional Commit messages.

Use these types when appropriate:

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `ci`
- `build`
- `chore`

If a change should trigger a release, prefer `feat` or `fix`.

## Pull Requests

- Keep PR titles and squash commit titles aligned when possible.
- Resolve review comments before merge.
- Validate the relevant local checks before pushing:
  - `uv run --group lint ruff check .`
  - `uv run --group test pytest -q`
  - `uv run --group docs zensical build`
