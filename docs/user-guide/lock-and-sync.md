# Lock & Sync

Every NSX app is reproducible through two files:

| File       | Purpose                                                              |
| ---------- | -------------------------------------------------------------------- |
| `nsx.yml`  | **Intent** — what modules the app needs and where they come from     |
| `nsx.lock` | **Receipt** — the exact commit + content hash of every vendored copy |

`nsx lock` writes (or refreshes) `nsx.lock`. `nsx sync` makes the on-disk
`modules/` tree match `nsx.lock` exactly. Use `nsx sync --frozen` in CI to
fail on drift instead of correcting it.

## The `source:` field

Each entry under `modules:` in `nsx.yml` may carry an optional `source:`
field that tells NSX where the module's contents come from.

| Form                              | Meaning                                                  |
| --------------------------------- | -------------------------------------------------------- |
| _omitted_                         | Registry default (git or packaged)                       |
| `source: { path: <path> }`        | Linked from an external directory; mirrored on each sync |
| `source: { vendored: true }`      | Committed inside this app; sync never touches it         |

### `source:` omitted (registry default)

```yaml
modules:
  - name: nsx-peripherals
    revision: main
    project: nsx-peripherals
```

NSX resolves the module against the packaged registry (or any
`module_registry.*` override in `nsx.yml`). If the project entry has a
`url`, it is git-cloned at the locked commit. If it points into the
neuralspotx package, it is copied. Both cases are gitignored under
`modules/.gitignore` because `nsx sync` re-acquires them.

### `source: { path: <p> }` — linked module

```yaml
modules:
  - name: my-driver
    source:
      path: ../../shared/my-driver
```

NSX treats the external path as the source of truth. `nsx sync` mirrors
its contents into `modules/my-driver/` (excluding `.git`/`__pycache__`),
hashes the result, and stores the hash in `nsx.lock`. The vendored copy
is gitignored; the source lives wherever you already source-control it.

### `source: { vendored: true }` — committed in this app

```yaml
modules:
  - name: my-aot-stub
    source:
      vendored: true
```

The directory under `modules/my-aot-stub/` is owned by you and committed
with the app. `nsx sync` will **never** write to it; the only thing
recorded in `nsx.lock` is the content hash, so drift is still detectable.

The fastest way to add one is:

```bash
nsx module add my-aot-stub --vendored
```

That scaffolds a minimal `nsx-module.yaml` + `CMakeLists.txt`, appends
the `source: { vendored: true }` entry to `nsx.yml`, regenerates
`modules/.gitignore` (so the directory is **kept** in git), and refreshes
`nsx.lock`.

Typical use cases:

- AOT-generated modules
- In-house drivers
- Customer-private modules that should not be re-fetched
- Snapshot of a third-party drop frozen for a release

## Lock kinds

`nsx.lock` records each module under one of five kinds:

| Kind         | Source                          | Sync behaviour                              |
| ------------ | ------------------------------- | ------------------------------------------- |
| `git`        | Registry git project            | Re-clone at the locked commit               |
| `packaged`   | Shipped inside neuralspotx      | Re-copy from the package                    |
| `local`      | `source: { path: }` (linked)    | Mirror from external path, hash-verify      |
| `vendored`   | `source: { vendored: true }`    | Hands-off; verify content hash only         |
| `unresolved` | Registry git, upstream offline  | Hash-verify only; cannot re-fetch           |

`nsx outdated` only operates on `git` modules — the others have no
upstream constraint to compare against.

## CI recipe

```bash
nsx lock --check            # fail if nsx.lock is stale relative to nsx.yml
nsx sync --frozen           # fail if modules/ drifts from nsx.lock
nsx outdated --exit-code    # fail if a git constraint has moved upstream
```

Together these guarantee that what was committed builds bit-for-bit
identically to what CI builds.

`nsx lock --check` is read-only: it resolves the lock as `nsx lock` would
and prints a structured diff (`+ added`, `- removed`, `~ changed`) against
the on-disk `nsx.lock` without writing anything. Exit code is non-zero on
drift.

For machine-readable output, `nsx outdated --json` emits:

```json
{
  "checked": [
    {"module": "...", "constraint": "main", "locked": "...", "upstream": "...", "status": "up-to-date", "url": "..."}
  ],
  "skipped": [{"module": "...", "reason": "..."}],
  "outdated_count": 0
}
```

Pipe through `jq` for status dashboards or PR-comment bots.
