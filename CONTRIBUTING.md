# Contributing to neuralspotx

This file is the entry point for working on NSX itself. If you are using NSX to
build an app, the documentation site is what you want:
<https://ambiqai.github.io/neuralspotx/>.

## Start with an issue

Every code change needs an issue first, so the reason for a change survives
longer than the pull request that made it. Open one at
[AmbiqAI/neuralspotx/issues](https://github.com/AmbiqAI/neuralspotx/issues)
describing the behavior you want changed and how you would know it worked. For
a bug, say which NSX version, host OS and board you are on.

Security problems do not go in an issue. See [SECURITY.md](SECURITY.md): report
privately through
[GitHub security advisories](https://github.com/AmbiqAI/neuralspotx/security/advisories/new)
or email [support@ambiq.com](mailto:support@ambiq.com).

## Set up a checkout

```bash
uv sync
source .venv/bin/activate
uv tool install pre-commit
pre-commit install
nsx doctor
```

One `pre-commit install` covers both the commit and push stages. The first run
builds gitleaks, which takes a few minutes and is cached afterwards.

## Run the checks

```bash
pre-commit run --all-files --hook-stage manual
uv run --group lint --group test ty check --error-on-warning src/neuralspotx tests
uv run --group test pytest -q
```

CI runs the same three. Run all of them for anything cross-cutting; a narrower
command is fine for a narrow change.

Details of what each pre-commit stage covers, and when to use `SKIP`, are in the
[contributing guides on the site](https://ambiqai.github.io/neuralspotx/guides/contribute/agent-guidance/).

## Documentation

The published site is an Astro project in `astro-site/`:

```bash
uv sync --group docs
npm --prefix astro-site ci
npm --prefix astro-site run dev
npm --prefix astro-site run validate
```

Most of the Reference and Modules sections are generated rather than written, so
read [docs/maintainers/docs-workflow.md](docs/maintainers/docs-workflow.md)
before adding a page.

## Commits and pull requests

- Work on a branch and open a pull request; do not push feature work to `main`.
- Squash merge, with a [Conventional Commit](https://www.conventionalcommits.org/)
  title, because Release Please derives the version bump and changelog from it.
  `feat:` and `fix:` move the version; `docs:`, `refactor:`, `test:`, `chore:`,
  `ci:` and `build:` do not.
- Do not hand-edit the version in `pyproject.toml`, `CHANGELOG.md` or `uv.lock`'s
  own package entry. Release Please and the release workflow own all three.
- Keep the pull request description explicit about behavior changes and why they
  are worth it.

## Guides for specific tasks

Published, because they are things a user may also need to do:

- [Agent guidance](https://ambiqai.github.io/neuralspotx/guides/contribute/agent-guidance/)
- [Adding a board](https://ambiqai.github.io/neuralspotx/guides/contribute/adding-a-board/)
- [Adding a module](https://ambiqai.github.io/neuralspotx/guides/contribute/adding-a-module/)
- [Releases and versioning](https://ambiqai.github.io/neuralspotx/reference/releases/)

Unpublished, in [`docs/maintainers/`](docs/maintainers/), because they describe
how the project is run rather than how the product is used:

- [`docs-workflow.md`](docs/maintainers/docs-workflow.md), how the site is built
  and validated
- [`releases.md`](docs/maintainers/releases.md), the release workflow's mechanics
- [`repo-layout.md`](docs/maintainers/repo-layout.md), what lives where
- [`module-coverage.md`](docs/maintainers/module-coverage.md), internal module
  coverage against neuralSPOT
- [`board-coverage.md`](docs/maintainers/board-coverage.md), packaged board
  definitions
- [`design-decisions.md`](docs/maintainers/design-decisions.md) and
  [`sdk-upstream-plan.md`](docs/maintainers/sdk-upstream-plan.md), why NSX is
  shaped the way it is

Architectural rules that agents and humans both have to follow are in
[AGENTS.md](AGENTS.md).
