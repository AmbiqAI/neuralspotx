# Migration: From Root `neuralSPOT` Coupling to NSX Module Contracts

## Objective

Move from monorepo-relative SDK path assumptions (for example
`../extern/AmbiqSuite/...`) to explicit NSX module/provider contracts that work
for out-of-tree apps and split repositories.

## Before

1. Board and module CMake files referenced AmbiqSuite via `NSX_MONOREPO_ROOT`.
2. SDK version/path assumptions were encoded in board files.
3. Module orchestration depended on in-repo layout.

## After

1. SDK selection is explicit via provider family (`NSX_SDK_PROVIDER`).
2. SDK root is explicit via provider-resolved variables:
   - `NSX_AMBIQSUITE_ROOT`
   - `NSX_AMBIQSUITE_VERSION`
3. Module compatibility is enforced through metadata:
   - `nsx-module.yaml`
   - `registry.lock.yaml`
   - app-local `nsx.yml`

## Migration Steps

1. Add provider modules and board constraints.
2. Refactor board/module CMake to consume `NSX_AMBIQSUITE_ROOT` instead of
   monorepo-relative AmbiqSuite paths.
3. Keep temporary fallback discovery for local development.
4. Move modules to split repos and update registry project mappings.
5. Remove fallback once split-repo workflows are stable.

## Compatibility Strategy

1. AP3 path is first-class decoupling target.
2. AP510 remains regression-supported.
3. AP4 enters as metadata/profile scaffolding before full bring-up.

## Tooling Implications

1. `nsx create-app/new` resolves starter profile including SDK provider.
2. `nsx module add/remove/update` uses hard-fail compatibility checks.
3. `nsx module register` enables custom module source attachment without editing
   packaged NSX registry data.
