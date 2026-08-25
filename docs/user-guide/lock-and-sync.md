# Lock & Sync

Every NSX app is reproducible through two files:

| File       | Purpose                                                              |
| ---------- | -------------------------------------------------------------------- |
| `nsx.yml`  | **Intent** — what modules the app needs and where they come from     |
| `nsx.lock` | **Receipt** — the exact commit + content hash of every vendored copy |

`nsx lock` writes (or refreshes) `nsx.lock`. `nsx sync` makes the on-disk
`modules/` tree match `nsx.lock` exactly. Use `nsx sync --frozen` in CI to
fail on drift instead of correcting it.

## Stable and development dependency modes

The packaged `stable` registry is the release default. Its project and module
revisions are expected to move to immutable version tags or full commit SHAs.
The SDK defaults are pinned to immutable releases (`nsx-ambiq-sdk@v5.2.24` and
`nsx-pmu-armv8m@v0.2.0`). The packaged `neuralspotx@main` self-reference is the
sole *permanent* floating-ref allowance. Any other floating stable ref must be
a temporary branch pin that carries an `expires_on` date in the registry
policy allowlist; adding one without a date is rejected, and once the date
passes `test_temporary_allowances_have_not_expired` fails until the pin is
collapsed to a tag or full SHA.

Internal target bring-up remains explicit and app-local. Use ordered
`registry.layers` (`workspace` or `inline`) for shared overlays, then
`module_registry` for the highest-precedence app override:

```yaml
registry:
  layers:
    - packaged
    - workspace: ../bringup-registry.yaml

module_registry:
  projects:
    nsx-ambiq-sdk:
      local_path: ../nsx-ambiq-sdk
```

Relative `local_path` values in inline layers and `module_registry` are resolved
from the app directory. In a workspace layer, they are resolved from the
workspace overlay file's directory, so shared overlays remain portable.

An explicit `local_path` overrides the project's packaged git URL and produces
a `local` lock entry with the source tree's content hash. For a branch or SHA
override, pinning the project revision is enough — an app-authored project pin
repins every module of that project, overriding the packaged registry's
module-level defaults:

```yaml
module_registry:
  projects:
    nsx-ambiq-sdk:
      revision: bringup/customer-board
```

Within one override source, a module-level `revision` outranks the
project-level one — but every module of a project is vendored from a single
shared clone, so **all modules of one project must resolve to one revision**.
Pinning one module of a multi-module project (such as the `nsx-ambiq-sdk`
modules) apart from its siblings makes two constraints claim the same
vendored path, which `nsx sync` rejects as a content conflict. A module-level
revision that differs from its project's pin is only coherent when the module
lives in its own single-module repository:

```yaml
module_registry:
  projects:
    nsx-ambiq-sdk:
      revision: bringup/customer-board  # repins every nsx-ambiq-sdk module together
  modules:
    nsx-pmu-armv8m:
      project: nsx-pmu-armv8m           # single-module repo: safe to pin on its own
      revision: fix/pmu-counter
```

Precedence is app-over-packaged first, module-over-project second: an
app-authored pin (project- or module-level, in `module_registry` or a
`registry.layers` entry) always beats the packaged registry's defaults, and
module-level beats project-level only within the same override source.
Between app-authored layers, the later layer wins even where an earlier
layer pinned a module explicitly; because that trades a specific pin for a
general one, `nsx` logs a warning naming the module, both revisions, and the
winning layer.

Regardless of mode, `nsx.lock` records exact resolved content: git refs resolve
to a commit SHA plus content hash, while local projects record a content hash.
SBOM output preserves the lock's project, kind, requested constraint/tag,
resolved commit (for git), and neuralspotx tool version. This makes branch and
local development inputs visible in provenance without changing stable
registry defaults.

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
  - name: nsx-uart
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
