---
title: Memory placement
description: Put code and data in the memory region you meant, using the NSX_MEM macros, and manage the caches that decide whether it matters.
---

By default the linker decides where your code and data land: constants go to
non-volatile memory, initialized data and the stack go to tightly coupled memory. That is
the right answer most of the time. This page is about the times it is not: a buffer that
has to be reachable by a peripheral, an inner loop you want executing out of ITCM, or a
working set you want in the larger, slower shared SRAM.

:::note[These macros come from a vendored module]
`nsx_mem.h` and `nsx_compiler.h` ship in the `nsx-core` module inside the SDK your app
vendors, under `modules/nsx-ambiq-sdk/modules/nsx-core/includes-api/`. The section names
each macro expands to are per-SoC, so read the copy in your own app before relying on a
specific one.
:::

## Placing something

Annotate the definition:

```c
#include "nsx_mem.h"

NSX_MEM_SRAM      uint8_t g_dma_buffer[4096];
NSX_MEM_SRAM_BSS  uint8_t g_scratch[16384];
NSX_MEM_FAST_CODE void hot_loop(void);
```

The macros are the portable spelling of a section attribute. Six are defined:

| Macro | What it selects |
| --- | --- |
| `NSX_MEM_NVM` | Non-volatile memory. Where `const` data goes already. |
| `NSX_MEM_FAST` | The fast default for initialized data, which is tightly coupled memory on every SoC NSX packages a board for. |
| `NSX_MEM_FAST_BSS` | The zero-initialized equivalent. |
| `NSX_MEM_SRAM` | Initialized data in shared SRAM. |
| `NSX_MEM_SRAM_BSS` | Zero-initialized data in shared SRAM. |
| `NSX_MEM_FAST_CODE` | Code, placed for fast fetch rather than left in NVM. |

Use `NSX_MEM_SRAM_BSS` rather than `NSX_MEM_SRAM` for anything large and zero-initialized.
Initialized data has to be copied out of NVM at startup, so a 16 KB initialized array
costs you 16 KB of NVM and the time to copy it, for a buffer you were going to overwrite.

`NSX_SRAM_BSS` and `NS_PUT_IN_TCM` are older spellings kept for compatibility; prefer the
`NSX_MEM_` names.

### What they expand to

Each macro resolves per SoC. On `apollo510` the mapping is:

```c
#define NSX_MEM__SEC_SRAM        ".shared"
#define NSX_MEM__SEC_SRAM_BSS    ".sram_bss"
#define NSX_MEM__SEC_FAST_CODE   ".itcm_text"
```

A companion set of `NSX_MEM__HAS_*` macros says whether a region exists on the target at
all, which is what lets a portable module ask before placing something. On an SoC without
a given region, the macro falls back to the default placement rather than failing to
build, so check `NSX_MEM__HAS_SRAM` and friends if placement is load bearing for you.

If you need a section the macros do not name, `nsx_compiler.h` has the raw attribute
wrappers, which work the same across GCC, Arm Compiler for Embedded and ATfE:

```c
#define NSX_SECTION(s)    __attribute__((section(s)))
#define NSX_ALIGNED(n)    __attribute__((aligned(n)))
#define NSX_USED          __attribute__((used))
#define NSX_WEAK          __attribute__((weak))
```

Pair `NSX_SECTION` with `NSX_USED` for anything the linker would otherwise garbage
collect.

## The regions you are placing into

Region names and sizes come from the linker script the board selects, which is a per-SoC
file inside the vendored `nsx-core` module. For Apollo510 the ITCM variant committed in
this repository as `examples/power_benchmark/linker_script_itcm.ld` declares:

```text
MCU_ITCM     (rwx) : ORIGIN = 0x00000000, LENGTH = 262144
MCU_MRAM     (rx)  : ORIGIN = 0x00410000, LENGTH = 4128768
MCU_TCM      (rwx) : ORIGIN = 0x20000000, LENGTH = 507904
SHARED_SRAM  (rwx) : ORIGIN = 0x20080000, LENGTH = 3145728
```

Those four numbers are that file's, for that SoC and that linker profile. Every other part
has its own script with its own values, and the MRAM origin in particular differs between
the bootloader and no-bootloader variants. Read your own build's script rather than
carrying these figures across parts. See
[Startup and linker](/neuralspotx/guides/system/startup-and-linker/) for which script your
board selects.

### When you run out

Overflowing a region is a link-time error naming the region and the limit, for example a
TCM overflow reported against that script's 507904 bytes. The options, in the order worth
trying:

1. Move large zero-initialized buffers to `NSX_MEM_SRAM_BSS`.
2. Reduce the stack or heap sizes the board's `board.cmake` passes to the startup code.
3. Stop placing code in ITCM that does not need to be there.

## Caches

Placement and caching interact: a region's access cost depends on whether the cache is on
and whether the data you are looking at is coherent with what a peripheral wrote.

`nsx_mem.h` declares the cache surface:

```c
uint32_t nsx_cache_enable(void);
void     nsx_cache_disable(void);
uint32_t nsx_cache_flush(void);
uint32_t nsx_cache_publish_writes(void);
uint32_t nsx_cache_invalidate_observed_data(void);
uint32_t nsx_cache_sync_shared_data(void);
```

Not every part implements every operation. The header exposes capability macros, so
portable code can test before calling. Each macro is always defined, as `1` or `0`, so
test it with `#if` rather than `#ifdef`:

| Macro | Meaning when 1 |
| --- | --- |
| `NSX_CACHE_HAS_PUBLISH_WRITES` | `nsx_cache_publish_writes()` is implemented. |
| `NSX_CACHE_HAS_INVALIDATE_OBSERVED` | `nsx_cache_invalidate_observed_data()` is implemented. |
| `NSX_CACHE_HAS_SYNC_SHARED` | `nsx_cache_sync_shared_data()` is implemented. |
| `NSX_CACHE_HAS_EXPLICIT_DCACHE` | The data cache can be controlled explicitly. |

An unimplemented operation returns `NSX_CACHE_UNSUPPORTED` rather than failing silently,
so a portable module can call and check instead of guarding every call site.

### The two cases that bite

- **You wrote a buffer, a peripheral reads it.** Call `nsx_cache_publish_writes()` before
  handing the buffer over, so your writes are visible outside the CPU.
- **A peripheral wrote a buffer, you read it.** Call
  `nsx_cache_invalidate_observed_data()` first, so you are not reading a stale line.

`nsx_cache_sync_shared_data()` covers both directions for shared-SRAM buffers where
ownership moves back and forth.

Caches are enabled through [system
initialization](/neuralspotx/guides/system/system-init/), by setting `enable_cache` in
`nsx_system_config_t` or by calling `nsx_cache_enable()` directly.

## Measure rather than assume

Whether moving something changes anything depends on the part, the clock, the cache state
and the access pattern. The repository ships two examples that measure instead of
guessing: `pmu_profiling` reads the Cortex-M55 PMU for cycles, cache hits and branch
mispredicts, and `power_benchmark` measures across active, idle and deep-sleep phases. See
[Examples](/neuralspotx/guides/examples/).
