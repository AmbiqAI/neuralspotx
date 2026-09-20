---
title: Multi-target and portability
description: How one app source tree builds for several boards, what stays shared, and how to handle the parts that genuinely have to differ.
---

An NSX app can declare several boards and build for each of them from one source tree. The
packaged examples do it, which is why `hello_world` runs on an Apollo510 EVB and an
Apollo4P board without two copies of the source.

## Declaring more than one target

```yaml
targets:
  default: apollo510_evb
  supported:
    - apollo510_evb
    - apollo510b_evb
    - apollo330mP_evb
    - apollo510dL_evb
    - apollo4p_blue_kxr_evb
```

`default` is what you get when you do not pass `--board`. `supported` is the set `--board`
will accept. The map form of `supported` additionally allows per-board SoC, profile and
toolchain overrides, for the cases where one target needs a different compiler than the
rest.

Adding a target is three steps: add the board, run `nsx lock` so it gets its own resolved
section, and build it. See
[Boards and targets](/neuralspotx/guides/apps/boards-and-targets/).

## What is shared and what is not

| Shared across targets | Per target |
| --- | --- |
| `src/` | `build/<board>/` |
| `CMakeLists.txt` | The resolved module set, one section per board in `nsx.lock` |
| `nsx.yml` | `boards/<board>/` |

Each board builds into its own directory, so switching targets never invalidates the
other one's tree. Each board resolves its own closure, so two boards on different SoC
families can land on different modules and different SDK revisions without either being
wrong.

## Keeping source portable

The first rule is to depend on a wrapper rather than on the SDK. A module that talks to
the HAL or the BSP wrapper works anywhere a wrapper exists; a module that includes vendor
SDK headers directly is bound to that SDK. See
[Module model](/neuralspotx/guides/concepts/module-model/).

The second rule is to keep divergence out of the source files. Preprocessor conditionals
spread: one `#ifdef` becomes six, and then nobody can read the file for any single part.
NSX provides a per-family overlay instead.

### Per-family source overlays

Put family-specific source in `src/<soc_family>/` and call the helper from your
`CMakeLists.txt`:

```cmake
nsx_target_soc_overlay(my_app)
```

The generated build exposes the resolved family as `NSX_SOC_FAMILY`, and the helper adds
`src/${NSX_SOC_FAMILY}/` to the target if that directory exists. If it does not, nothing
happens, so the same `CMakeLists.txt` works for a target that needs no overlay and one
that does.

The shape that follows is a portable `src/` with a small per-family directory beside it,
which keeps the shared path readable and makes the divergence visible in the directory
listing rather than buried in a conditional.

### Per-target linker overlays

When a target needs a layout of its own:

```cmake
nsx_target_linker_overlay(my_app "${CMAKE_CURRENT_SOURCE_DIR}/linker_script_itcm.ld")
```

The helper fails loudly if the target or the script does not exist, rather than silently
linking with the board's default. The `power_benchmark` example uses this to run from
ITCM. See [Startup and linker](/neuralspotx/guides/system/startup-and-linker/).

## Where portability stops

Two things do not port, and no amount of structure changes that.

**Peripheral availability.** A module that needs a radio, a PDM microphone or an NPU will
not resolve for a board without one. That is what `compatibility.boards` and
`compatibility.socs` exist to express, and it is why adding a target fails at `nsx lock`
rather than at the compiler.

**Memory layout.** Region names, sizes and the bootloader variant differ per part. Code
placed with the `NSX_MEM_` macros ports because the macros resolve per SoC; code that
names a raw section or assumes a size does not. See
[Memory placement](/neuralspotx/guides/system/memory-placement/).

## Declared, not validated

An app declaring five supported targets means the module graph resolves for five targets.
It does not mean the firmware was run on five boards. The same applies to every
compatibility list in a module or board manifest. Treat a supported target as a build you
can attempt, and test it on the hardware before you claim it works there.
