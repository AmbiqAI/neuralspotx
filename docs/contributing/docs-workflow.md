# Docs Workflow

NSX documentation is published from the docs site in this repo.

## Local Workflow

Install docs dependencies:

```bash
cd <nsx-repo>
uv sync --group docs
```

Serve locally:

```bash
cd <nsx-repo>
uv run --group docs zensical serve
```

Build locally:

```bash
cd <nsx-repo>
uv run --group docs zensical build
```

## Writing Rules

- no absolute local filesystem paths
- no temp-path examples
- user-facing docs should describe the current NSX flow only
- contributor notes belong in the Contributing section
- task pages should favor workflow over exhaustive command narration
