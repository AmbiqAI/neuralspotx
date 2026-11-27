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
- `operations/_debug_backend.py` dispatches board operations through typed flash,
  reset, SWO and RTT handlers. The flash workflow owns build selection and frozen
  checks. Its driver prepares the final build generation and supplies a private
  image and programmer for the duration of the call. The J-Link implementation
  consumes the existing CMake v1 capture and returns the original artifact and
  recipe paths. Keep probe identity parsing and programming confirmation in the
  tool implementation.
