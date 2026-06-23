# Multi-Target & Portability

NSX examples can target a family of near-identical Apollo parts (e.g.
`apollo510_evb`, `apollo510b_evb`, `apollo330mP_evb`, `apollo510dL_evb`)
from a single source tree. This page describes the model and the two
escape hatches for the small amount of code that genuinely diverges.

## Lean, multi-target manifests

An app declares its build targets in `nsx.yml`:

```yaml
project:
  name: my_app
toolchain: arm-none-eabi-gcc
targets:
  default: apollo510_evb
  supported:
    - apollo510_evb
    - apollo510b_evb
    - apollo330mP_evb
modules:               # direct deps, additive on every target's board profile
  - nsx-timer
```

- The resolved module closure is **not** inlined; it is expanded from each
  board's derived `<board>_minimal` profile at lock time (profile-seeded
  resolution). See [Dependency Model](dependency-model.md) for the full model.
- Each supported board has its own section in the combined `nsx.lock`, so
  every target is independently reproducible.
- `nsx build` uses `targets.default`; `nsx build --board <sibling>` selects
  another and builds into `build/<board>/`.

## Per-target compatibility validation

When a board is locked, every resolved module's `nsx-module.yaml`
`compatibility` block (`boards` / `socs` / `toolchains`, where `"*"` matches
anything) is intersected against that target. A board listed in
`targets.supported` that a required module does not actually support fails
`nsx lock` fast, instead of surfacing as a cryptic downstream build error.

Set `NSX_SKIP_COMPAT_CHECK=1` to bypass the gate in an emergency.

## Keeping source portable

Route peripheral access through the HAL modules (`nsx-soc-hal`, the SoC
HAL/BSP) so application source stays SoC-agnostic. For the unavoidable
divergence, prefer one of the two mechanisms below over `#ifdef` soup.

### Per-target source overlays

Place shared code under `src/` and family-specific code under
`src/<soc_family>/`:

```
src/                # shared, SoC-agnostic
src/apollo5/        # compiled only when NSX_SOC_FAMILY == apollo5
src/apollo330/      # compiled only when NSX_SOC_FAMILY == apollo330
```

Then, after `add_executable()`:

```cmake
nsx_target_soc_overlay(my_app)
```

The helper compiles only the overlay matching the active board's
`NSX_SOC_FAMILY` and is a no-op when no overlay directory exists. For
finer-grained branching, `NSX_SOC_FAMILY` is also available directly:

```cmake
if(NSX_SOC_FAMILY STREQUAL "apollo330")
    target_compile_definitions(my_app PRIVATE MY_APP_LP_PATH)
endif()
```

### Per-target linker-script overlays

To swap the board's default linker script for an app-specific one (e.g. an
ITCM-execution layout), use:

```cmake
nsx_target_linker_overlay(my_app "${CMAKE_CURRENT_LIST_DIR}/linker_script_itcm.ld")
```

This replaces the `-T` option on the active board's flags target (the board
flags target appends after the app's own options, so the override must live
there). armclang scatter overlays are not yet supported — the helper warns
and keeps the board default. See `examples/power_benchmark` for a working
use.

## Scope

Portability is scoped to a family of near-identical parts. Spanning very
different generations (e.g. Apollo3 → Apollo5) in a single example is a
non-goal; bring a new SoC family up as its own board descriptors + profiles
first, then add it to an example's `targets.supported`.
