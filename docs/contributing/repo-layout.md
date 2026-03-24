# Repo Layout

The NSX tooling repo owns:

- `src/neuralspotx/`
- `docs/`
- `mkdocs.yml`
- packaged templates
- packaged CMake helpers
- built-in board definitions

Sibling areas commonly used during development:

- `nsx-modules/` for module repos
- `nsx-apps/` for generated and smoke-test apps

## Important Boundaries

- tooling and docs live in the NSX repo
- firmware modules live in separate repos
- generated apps are treated as independent buildable artifacts
