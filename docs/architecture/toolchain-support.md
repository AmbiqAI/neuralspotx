# Toolchain Support

NSX supports two toolchains for building firmware:

| Toolchain | Compiler | Linker | Binary Tool | Key |
|-----------|----------|--------|-------------|-----|
| **GCC** (default) | `arm-none-eabi-gcc` | `arm-none-eabi-ld` | `objcopy` / `size` | `arm-none-eabi-gcc` or `gcc` |
| **Arm Compiler 6** | `armclang` | `armlink` | `fromelf` | `armclang` |

## Selecting a Toolchain

### Via `nsx.yml`

Set the top-level `toolchain` field:

```yaml
toolchain: armclang   # or arm-none-eabi-gcc (default)
```

### Via CLI

Any build command accepts `--toolchain`:

```bash
nsx configure --toolchain armclang
nsx build --toolchain armclang
```

The CLI flag overrides `nsx.yml`.

### Via CMake Presets

The `CMakePresets.json` template includes presets for both toolchains:

```bash
cmake --preset gcc-ninja       # GCC + Ninja
cmake --preset armclang-ninja  # Arm Compiler 6 + Ninja
```

## How It Works

### Toolchain Detection

`nsx_toolchain_flags.cmake` auto-detects the active toolchain from `CMAKE_C_COMPILER_ID`:

- `GNU` → `NSX_TOOLCHAIN_FAMILY = "gcc"`
- `ARMClang` / `ArmClang` → `NSX_TOOLCHAIN_FAMILY = "armclang"`

Board files and the bootstrap use `NSX_TOOLCHAIN_FAMILY` for conditional logic.

### Board-Level Selection

Each `board.cmake` conditionally selects:

- **Startup source**: `startup_gcc.c` vs `startup_keil6.c`
- **Linker script**: `.ld` (GCC) vs `.sct` scatter file (armclang)

These live under `nsx-core/src/<soc>/gcc/` and `nsx-core/src/<soc>/armclang/`.

### Compile & Link Flags

`nsx_apply_toolchain_flags()` sets flags per toolchain:

| Aspect | GCC | armclang |
|--------|-----|----------|
| Optimization | `-O3 -ffast-math` | `-Ofast` |
| Sections | `-ffunction-sections -fdata-sections` | `-ffunction-sections -fdata-sections` |
| Short enums | default (arm-none-eabi) | `-fshort-enums` (matches SDK libs) |
| GC unused | `-Wl,--gc-sections` | `--remove` |
| Entry point | `-Wl,--entry,Reset_Handler` | `--entry=Reset_Handler` |
| Linker script | `-T<path>.ld` | `--scatter=<path>.sct` |
| Newlib wraps | `-Wl,--wrap=_write_r,...` | *(not needed)* |
| Stdlib | `-lm -lc -lgcc -lnosys -lstdc++` | *(built-in runtime)* |
| Binary gen | `objcopy -Obinary` | `fromelf --bin` |
| Size report | `arm-none-eabi-size` | `fromelf --text -z` |

### Compile Definitions

| Definition | Set When |
|-----------|----------|
| `gcc` | GCC toolchain (legacy compat) |
| `NSX_TOOLCHAIN_ARMCLANG` | armclang toolchain |

## Portable Compiler Abstractions

`nsx_compiler.h` (in `nsx-core`) provides portable macros for compiler-specific attributes:

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
| `NSX_COMPILER_GCC` | GCC or compatible (`__GNUC__` without `__clang__`) |
| `NSX_COMPILER_ARMCLANG` | Arm Compiler 6 (`__ARMCC_VERSION >= 6000000`) |
| `NSX_HAS_NEWLIB` | Only true for GCC (newlib retarget stubs available) |

## SoC / Board Coverage

armclang is validated on Apollo510 (Cortex-M55) and declared supported by the
Apollo5a/Apollo5b/Apollo510L/Apollo510B and Apollo330mP EVBs (their
`nsx-module.yaml` lists `armclang` under `compatibility.toolchains`).

Apollo3/Apollo3p/Apollo4* boards currently declare only `arm-none-eabi-gcc`:

- Apollo3 / Apollo3p: no armclang startup/scatter files in `nsx-core` yet.
- Apollo4l / Apollo4p / Apollo4b-blue: armclang ships only an assembly startup
  (`startup_keil6.s`) instead of the `.c` variant NSX board files wire up, and
  only a `linker_script.sct` (no `_sbl` variant). Adding armclang here is a
  matter of supplying the missing `startup_armclang.c` + `linker_script_sbl.sct`
  under `nsx-core/src/<soc>/armclang/`.

## Notes

- Pre-built SDK libraries (`libam_hal.a`, `libam_bsp.a`) are GCC-compiled but
  are ABI-compatible with armclang-compiled code. The alternate Keil `*.lib`
  archives are **not** compatible — they carry `Tag_ABI_HardFP_use = 1` which
  clashes with armclang's default output attributes (L6242E). NSX therefore
  always links the `.a` variants regardless of toolchain.
- `nsx_toolchain_flags.cmake` passes `-fshort-enums` when building with
  armclang to match the enum ABI used by the prebuilt `.a` libraries.
