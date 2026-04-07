# Memory Placement

NSX provides portable memory-placement macros in `nsx_mem.h` that let you
control where variables and code are physically located — without writing
SoC-specific linker attributes.

## Why It Matters

Ambiq SoCs have multiple memory regions with very different performance
and capacity characteristics:

| Region | Apollo510 | Access speed | Typical use |
|--------|----------|-------------|-------------|
| **MRAM** (flash) | 4 MB | Slow (wait states) | Code, const data |
| **TCM** | 496 KB | Fast (0 wait) | Stack, heap, .data, .bss |
| **ITCM** | 256 KB | Fast (0 wait) | Hot code paths |
| **Shared SRAM** | 3 MB | Medium (1+ wait) | Large buffers, model weights |

Placing data in the wrong region can mean the difference between 21 ms and
74 ms inference time — a 3.5x difference — with no code changes.

## Macros

| Macro | Where it goes | Initialized | Use case |
|-------|--------------|-------------|----------|
| `NSX_MEM_NVM` | MRAM (flash) | In-place | Large const data (LUTs, tables) |
| `NSX_MEM_FAST` | TCM | Copied from NVM | Fast initialized data |
| `NSX_MEM_FAST_BSS` | TCM | Zeroed | Fast uninitialized data |
| `NSX_MEM_SRAM` | Shared SRAM | Copied from NVM | Large initialized buffers, model weights |
| `NSX_MEM_SRAM_BSS` | Shared SRAM | Zeroed | Tensor arenas, DMA buffers, scratch space |
| `NSX_MEM_FAST_CODE` | ITCM/DTCM/TCM | Copied from NVM | Hot inner loops, ISRs |

## Usage

Place the macro before the type, after any storage class:

```c
#include "nsx_mem.h"

// 64 KB tensor arena in shared SRAM — zeroed at boot, no copy cost
NSX_MEM_SRAM_BSS alignas(16) static uint8_t g_arena[65536];

// Model weights in shared SRAM — copied from flash at boot
NSX_MEM_SRAM alignas(16) static const uint8_t g_model[] = { 0x1c, 0x00, ... };

// Hot inference kernel in ITCM — 0-wait-state code execution
NSX_MEM_FAST_CODE void my_fast_kernel(void) { ... }

// Large LUT kept in flash — don't waste RAM
NSX_MEM_NVM const int16_t g_lut[8192] = { ... };
```

## SoC Support Matrix

Macros degrade gracefully — on SoCs without a particular memory region, the
macro expands to nothing and the variable goes to the default section.

| Macro | Apollo3 | Apollo3P | Apollo4P | Apollo510 | Apollo330P |
|-------|---------|----------|----------|-----------|------------|
| `NSX_MEM_SRAM` | default | default | `.shared` | `.shared` | `.shared` |
| `NSX_MEM_SRAM_BSS` | default | default | `.sram_bss` | `.sram_bss` | `.sram_bss` |
| `NSX_MEM_FAST_CODE` | default | `.tcm` | default | `.itcm_text` | `.dtcm_text` |
| `NSX_MEM_FAST` | default | default | default | default | default |
| `NSX_MEM_FAST_BSS` | default | default | default | default | default |

"default" means the compiler's normal `.data` or `.bss` section (typically in TCM).

## Linker Section Mapping

Each macro targets a specific linker output section. These must exist in your
linker script:

```
Macro              → Section       → Memory Region    → Boot action
─────────────────────────────────────────────────────────────────────
NSX_MEM_SRAM       → .shared       → SHARED_SRAM      → Copy from MRAM
NSX_MEM_SRAM_BSS   → .sram_bss     → SHARED_SRAM      → Zeroed
NSX_MEM_FAST_CODE  → .itcm_text    → MCU_ITCM         → Copy from MRAM
NSX_MEM_FAST       → .data         → MCU_TCM           → Copy from MRAM
NSX_MEM_FAST_BSS   → .bss          → MCU_TCM           → Zeroed
NSX_MEM_NVM        → .rodata       → MCU_MRAM          → In-place
```

## Cache Helpers

`nsx_mem.h` also provides lightweight cache control:

```c
uint32_t nsx_cache_enable(void);   // Enable I/D cache (or unified cache on AP3/AP4)
void     nsx_cache_disable(void);
```

Returns 0 on success. On Apollo5, returns non-zero if the cache power domain
(CPDLP) is not active — call `nsx_hw_init()` or `nsx_minimal_hw_init()`
first.

On Apollo3, these are no-ops. On Apollo4, they configure the unified cache.

## Practical Guidance

### Model weights: TCM vs SRAM

For small models (under ~200 KB), place weights in **TCM** for 0-wait-state
access. This is the default — just declare the array normally.

For large models, use `NSX_MEM_SRAM` to avoid overflowing TCM. The tradeoff
is slightly higher access latency (partially mitigated by D-cache).

```c
// Small model — stays in TCM (fast, limited capacity)
static const uint8_t small_model[] = { ... };

// Large model — goes to shared SRAM (more room, slightly slower)
NSX_MEM_SRAM static const uint8_t large_model[] = { ... };
```

### Tensor arenas

Tensor arenas don't need initialization — use `NSX_MEM_SRAM_BSS` or
`NSX_MEM_FAST_BSS` to avoid boot-time copy cost:

```c
// In SRAM if it's too big for TCM
NSX_MEM_SRAM_BSS alignas(16) static uint8_t arena[256 * 1024];

// In TCM if it fits (faster, recommended for small arenas)
NSX_MEM_FAST_BSS alignas(16) static uint8_t arena[64 * 1024];
```

### Hot code in ITCM

On Apollo510, TFLM kernel code can be placed in ITCM for faster execution.
The `linker_script_itcm_sbl.ld` variant uses KEEP directives to pull
specific object files into ITCM:

```
KEEP(conv*.o      (.text .text.* .rodata .rodata.*))
KEEP(softmax*.o   (.text .text.* .rodata .rodata.*))
```

For your own hot functions, use `NSX_MEM_FAST_CODE`:

```c
NSX_MEM_FAST_CODE void my_dsp_kernel(int16_t *buf, size_t len) {
    // Runs from ITCM — 0-wait-state fetch
}
```

!!! warning "ITCM is limited"
    Apollo510 ITCM is 256 KB. Placing too much code there will cause a
    linker overflow error. Profile first, then move only the hottest paths.

## Backward Compatibility

Legacy macros are mapped to the new system:

| Legacy | Maps to |
|--------|---------|
| `AM_SHARED_RW` | `NSX_MEM_SRAM` |
| `NS_SRAM_BSS` | `NSX_MEM_SRAM_BSS` |
| `NS_PUT_IN_TCM` | `NSX_MEM_FAST` |

Prefer `NSX_MEM_*` in new code.
