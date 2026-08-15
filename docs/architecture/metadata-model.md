# Metadata Model

NSX uses three metadata layers.

## 1. Module Metadata: `nsx-module.yaml`

Owned by each module repo.

Declares:

1. module identity, type, and version
2. backend support flags
3. CMake package and target contract
4. required and optional module dependencies
5. compatibility constraints for board, SoC, and toolchain

## 2. Curated Lock Metadata: `neuralspotx.data/registry.lock.yaml`

Owned by the NSX tooling repo.

Declares:

1. channels such as `stable` and `preview`
2. known module entries and project mapping
3. starter profiles per board
4. default SDK provider revisions for supported boards

## 3. App Metadata: `nsx.yml`

Owned by each generated app.

Declares:

1. project name
2. target board and SoC
3. toolchain, channel, and profile
4. enabled modules and revisions
5. optional app-local module registry overrides

## Project Record Lifecycle

`registry.lock.yaml` has two independent maps: `projects` (git/packaged
sources) and `modules` (module name → `project` + `revision` + `metadata`
path). A module's `project` field is looked up by name in `projects` at
resolution time — nothing iterates `projects` up front, so during automatic
module resolution a `projects` entry is only ever reached when some
`modules.<name>.project`, `soc_families.<family>.project`,
`starter_profiles.<profile>.project_overrides`, or
`starter_profiles.<profile>.module_overrides.<name>.project` field names it.
(`nsx module register --project <existing-name>` can also deliberately reuse
an existing `projects` record as its source without a module or profile
naming it first — see "Working with Modules" below — so a record can be
structurally unreached today and still be a legitimate, intentionally kept
reuse target; that is what `RESERVED_REGISTRY_PROJECT_NAMES` documents when
it applies.)

This means consolidating a module's source into another project (e.g. a
one-repo-per-module layout absorbed into a monorepo such as
`nsx-ambiq-sdk`) is a **two-part edit**: repoint the `modules.<name>.project`
field *and* delete the old `projects.<name>` record in the same change.
Leaving the old record behind doesn't break anything at runtime (it is
simply never read during automatic resolution), but it rots silently —
pointing at a URL that may no longer exist, be renamed, or be archived —
until someone tries to reuse it as a `--project` reference or a
`module_registry` override anchor.

`neuralspotx.registry_policy.orphaned_registry_project_report` enforces this
contract structurally (deterministic, no network) and runs in
`tests/test_stable_registry_policy.py`. `scripts/audit_registry_project_urls.py`
is the companion *network* audit: it checks that every project's git URL is
actually reachable, with an explicit, documented exemption for
packaged/self-referential projects (`neuralspotx`) that never need a network
clone in the built-in flow. Run it manually or from a scheduled job — it is
intentionally not part of the normal (network-free) unit-test suite.

If a project record is ever intentionally kept without being referenced —
e.g. as a documented backward-compatible override anchor so
`module_registry.modules.<name>.project: <name>` keeps working for apps that
pin it without also supplying a `module_registry.projects.<name>` stanza —
add its name to `registry_policy.RESERVED_REGISTRY_PROJECT_NAMES` with a
comment explaining the contract. That set is empty today: no first-class
module currently needs it. Once a reservation is no longer needed (the
project record itself was deleted), remove its name from
`RESERVED_REGISTRY_PROJECT_NAMES` in the same change — a stale reservation
is reported the same way a stale immutable-ref allowance is.

## Resolution Order

1. load the curated lock registry
2. merge app-local `module_registry` overrides
3. resolve the requested module and required dependency closure
4. validate compatibility against the app target
5. materialize source content from curated module locations
6. copy or replace vendored `modules/` and `boards/` content inside the app
7. update `nsx.yml` and generated `cmake/nsx/modules.cmake`

Step 2 enforces a two-axis revision precedence: **across sources**, an
app-authored override layer (a `registry.layers` entry or the
`module_registry` block) beats the packaged registry and the synthetic
starter-profile defaults — a layer that pins `projects.<p>.revision` repins
every module of `<p>` in the effective registry; **within one source**,
module-level beats project-level — a layer's own `modules.<name>.revision`
outranks that same layer's project pin. Module revision selection itself
reads only the merged `modules.<name>.revision` field
(`registry_entry_for_module`), so this propagation
(`project_config._propagate_layer_project_pins`) is what makes app project
pins effective; without it a packaged module-level default would silently
outrank an explicit app pin (issue #218).

The metadata model drives orchestration. CMake remains authoritative for the
actual build graph.
