# Toolchain Support

NSX supports three toolchains for building firmware:

| Toolchain | Compiler | Linker | Binary Tool | Key | Status |
|-----------|----------|--------|-------------|-----|--------|
| **GCC** (default) | `arm-none-eabi-gcc` | `arm-none-eabi-ld` | `objcopy` / `size` | `arm-none-eabi-gcc` or `gcc` | Stable |
| **Arm Compiler 6** | `armclang` | `armlink` | `fromelf` | `armclang` | Stable |
| **ATfE** (LLVM Embedded) | `clang` | `ld.lld` | `llvm-objcopy` / `llvm-size` | `atfe` | **Experimental** |

!!! warning "ATfE is experimental"
    ATfE (Arm Toolchain for Embedded) builds and runs correctly on Apollo5
    targets, but has not been validated as extensively as GCC or armclang.
    Use it for evaluation; production deployments should use GCC or armclang.

**ATfE** is the [Arm Toolchain for Embedded](https://github.com/arm/arm-toolchain)
— Arm's LLVM-based bare-metal toolchain (clang + lld + compiler-rt + picolibc
with a newlib overlay). It is a free, open-source alternative to Arm Compiler 6.

## Selecting a Toolchain

### Via `nsx.yml`

Set the top-level `toolchain` field:

```yaml
toolchain: armclang   # or arm-none-eabi-gcc (default) or atfe
```

### Via CLI

Any build command accepts `--toolchain`:

```bash
nsx configure --toolchain armclang
nsx build --toolchain atfe
```

The CLI flag overrides `nsx.yml`.

### Via CMake Presets

The `CMakePresets.json` template includes presets for each toolchain:

```bash
cmake --preset gcc-ninja        # GCC + Ninja
cmake --preset armclang-ninja   # Arm Compiler 6 + Ninja
cmake --preset atfe-ninja       # ATfE (clang + lld) + Ninja
```

## Installing ATfE

1. Download the appropriate build from the
   [Arm Toolchain for Embedded releases](https://github.com/arm/arm-toolchain/releases).
2. Extract it to a stable location (e.g. `/Applications/ATFEToolchain/ATfE-22.1.0`
   on macOS or `/opt/ATfE-22.1.0` on Linux).
3. Set `ATFE_ROOT` so the toolchain file can locate `clang`, `lld`, and the
   `newlib.cfg` bundled config:

   ```bash
   export ATFE_ROOT="/Applications/ATFEToolchain/ATfE-22.1.0"
   ```

   Add the line to `~/.zshrc` / `~/.bashrc` for persistence. ATfE does **not**
   need to be on `PATH`; NSX invokes its binaries by absolute path.
4. Run `nsx doctor` to verify the install.

## How It Works

### Toolchain Detection

`nsx_toolchain_flags.cmake` auto-detects the active toolchain from
`CMAKE_C_COMPILER_ID`:

- `GNU` → `NSX_TOOLCHAIN_FAMILY = "gcc"`
- `ARMClang` / `ArmClang` → `NSX_TOOLCHAIN_FAMILY = "armclang"`
- `Clang` (without `__ARMCC_VERSION`) → `NSX_TOOLCHAIN_FAMILY = "atfe"`

Board files and the bootstrap use `NSX_TOOLCHAIN_FAMILY` for conditional logic.

### Board-Level Selection

Each `board.cmake` conditionally selects:

- **Startup source**: `startup_gcc.c` (GCC and ATfE) vs `startup_keil6.c` (armclang)
- **Linker script**: `.ld` (GCC and ATfE, consumed by `ld.lld` in GNU-compat mode)
  vs `.sct` scatter file (armclang)

ATfE reuses the GCC `startup_gcc.c` and `.ld` linker scripts — `lld` accepts
GNU ld linker scripts, and clang accepts the GCC-style `__attribute__((naked))`
used by the startup. These live under `nsx-core/src/<soc>/gcc/` and
`nsx-core/src/<soc>/armclang/`.

### Compile & Link Flags

`nsx_apply_toolchain_flags()` sets flags per toolchain:

| Aspect | GCC | armclang | ATfE |
|--------|-----|----------|------|
| Optimization | `-O3 -ffast-math` | `-Ofast` | `-O3 -ffast-math` |
| Sections | `-ffunction-sections -fdata-sections` | same | same |
| Short enums | default | `-fshort-enums` (matches SDK libs) | `-fshort-enums` |
| Short wchar | *(no — 32-bit, matches `.a`)* | `-fshort-wchar` (16-bit, matches `.lib`) | *(no — 32-bit, matches `.a`)* |
| GC unused | `-Wl,--gc-sections` | `--remove` | `-Wl,--gc-sections` |
| Entry point | `-Wl,--entry,Reset_Handler` | `--entry=Reset_Handler` | `-Wl,--entry,Reset_Handler` |
| Linker script | `-T<path>.ld` | `--scatter=<path>.sct` | `-T<path>.ld` |
| Newlib wraps | `-Wl,--wrap=_write_r,...` | *(not needed)* | `-Wl,--wrap=...` (picolibc+newlib overlay) |
| Stdlib | `-lm -lc -lgcc -lnosys -lstdc++` | *(built-in runtime)* | `-lm -lc -lnosys` |
| Binary gen | `objcopy -Obinary` | `fromelf --bin` | `llvm-objcopy -Obinary` |
| Size report | `arm-none-eabi-size` | `fromelf --text -z` | `llvm-size` |

### Compile Definitions

| Definition | Set When |
|-----------|----------|
| `gcc` | GCC toolchain (legacy compat) |
| `NSX_TOOLCHAIN_ARMCLANG` | armclang toolchain |
| `NSX_TOOLCHAIN_ATFE` | ATfE toolchain |

## Portable Compiler Abstractions

`nsx_compiler.h` (in `nsx-core`) provides portable macros for compiler-specific
attributes:

```c
#include "nsx_compiler.h"

// Section placement
NSX_SECTION(".itcm_text") void fast_function(void) { ... }

// Common attributes
NSX_USED static const int keep_me = 42;
NSX_WEAK void optional_handler(void) { }
NSX_ALIGNED(16) uint8_t buffer[256];
NSX_NORETURN void fatal_error(void);
NSX_ALWAYS_INLINE static inline int add(int a, int b) { return a + b; }

// Packed structures
NSX_PACKED_BEGIN
typedef struct NSX_PACKED_ATTR {
    uint8_t  type;
    uint32_t value;
} my_packed_t;
NSX_PACKED_END

// Conditional newlib usage
#if NSX_HAS_NEWLIB
#include <sys/types.h>
#endif
```

### Detected Compiler Macros

| Macro | Meaning |
|-------|---------|
| `NSX_COMPILER_GCC` | GCC (`__GNUC__` without `__clang__`) |
| `NSX_COMPILER_ARMCLANG` | Arm Compiler 6 (`__ARMCC_VERSION >= 6000000`) |
| `NSX_COMPILER_CLANG` | ATfE / vanilla clang (`__clang__` without `__ARMCC_VERSION`) |
| `NSX_HAS_NEWLIB` | True for GCC and ATfE (newlib retarget stubs available) |

## SoC / Board Coverage

**armclang** is validated on Apollo510 (Cortex-M55) and declared supported by
the Apollo5a/Apollo5b/Apollo510L/Apollo510B and Apollo330mP EVBs.
**ATfE** builds correctly on the same targets but is considered **experimental**
(limited on-device validation).

Apollo3/Apollo3p/Apollo4* boards currently declare only `arm-none-eabi-gcc`:

- Apollo3 / Apollo3p: no armclang startup/scatter files in `nsx-core` yet.
  ATfE would work in principle (it reuses the GCC startup/linker script) but
  has not been validated on these parts.
- Apollo4l / Apollo4p / Apollo4b-blue: armclang ships only an assembly startup
  (`startup_keil6.s`) instead of the `.c` variant NSX board files wire up, and
  only a `linker_script.sct` (no `_sbl` variant). Adding armclang here is a
  matter of supplying the missing `startup_armclang.c` + `linker_script_sbl.sct`
  under `nsx-core/src/<soc>/armclang/`. ATfE would also need validation.

## Notes

### Pre-built Library Selection

AmbiqSuite ships two sets of pre-built HAL/BSP libraries per SoC:

| Format | Compiler | `wchar_t` ABI | Used by |
|--------|----------|---------------|----------|
| `.a` (ELF archive) | GCC | 32-bit (`Tag_ABI_PCS_wchar_t=4`) | GCC, ATfE |
| `.lib` (ARM archive) | Keil/armclang | 16-bit (`Tag_ABI_PCS_wchar_t=2`) | armclang |

The `nsx-ambiq-hal-*` and `nsx-ambiq-bsp-*` modules select the correct format
automatically based on `NSX_TOOLCHAIN_FAMILY`.

### `-fshort-wchar` (armclang only)

The armclang `.lib` prebuilts are compiled with `-fshort-wchar` (16-bit
`wchar_t`), matching Ambiq's Keil project settings. NSX passes `-fshort-wchar`
to application code **only** when building with armclang, so the ABI matches.
GCC and ATfE link against the `.a` archives (32-bit `wchar_t`) and do **not**
use `-fshort-wchar`.

!!! note
    Ambiq's upstream GCC Makefile also omits `-fshort-wchar`, so this per-
    toolchain split is consistent with the vendor's own build configuration.

### Other ABI Flags

- `nsx_toolchain_flags.cmake` passes `-fshort-enums` when building with
  armclang or ATfE to match the enum ABI used by the prebuilt libraries.
- ATfE uses its bundled `picolibc` configured with a newlib-compatibility
  overlay (via `--config=newlib.cfg` from the toolchain directory), which is why
  `NSX_HAS_NEWLIB` is true and the same `_write_r` / `_read_r` retarget wraps
  used by GCC apply unchanged.
