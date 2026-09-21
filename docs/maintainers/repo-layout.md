# Repo Layout

The NSX tooling repo owns:

- `src/neuralspotx/`
- `astro-site/`, the published documentation site
- `docs/maintainers/`, unpublished maintainer Markdown
- packaged templates
- packaged CMake helpers
- built-in board definitions

After `nsx create-app`, a generated app contains:

- `nsx.yml` for app metadata and module state
- `modules/` for vendored module content
- `boards/` for vendored board definitions
- `cmake/nsx/` for copied build helpers
- `src/` for app-owned source code

## Important Boundaries

- tooling and docs live in the NSX repo
- built-in module source repos are cloned on demand from their upstream URLs
- generated apps are treated as independent buildable artifacts
