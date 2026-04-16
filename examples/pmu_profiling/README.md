# pmu_profiling

Demonstrates the **nsx-pmu-armv8m** module on the Apollo510 EVB.  Configures
the Arm Cortex-M55 Performance Monitoring Unit (PMU) with the *BASIC_CPU*
preset and profiles a tight integer workload, printing counter values over
SWO every 2 seconds.

## What is the PMU?

The Cortex-M55 has a hardware PMU with 8 configurable event counters plus a
dedicated cycle counter.  Each counter can be assigned to any of ~70 hardware
events (cache misses, stalls, MVE instructions, bus accesses, etc.).  The
**nsx-pmu-armv8m** module provides a simple C API to configure, read, and
print these counters.

### Built-in Presets

| Preset | Counters (4 × 32-bit) |
|--------|----------------------|
| `NS_PMU_PRESET_BASIC_CPU` | CPU cycles, instructions retired, frontend stalls, backend stalls |
| `NS_PMU_PRESET_MEMORY` | Memory accesses, L1 D-cache refills, bus accesses, bus cycles |
| `NS_PMU_PRESET_MVE` | MVE instructions, MVE int MACs, MVE multi-reg loads/stores, MVE stalls |
| `NS_PMU_PRESET_ML_DEFAULT` | MVE instructions, MVE int MACs, instructions retired, bus cycles |

You can also configure individual events from any of the 70+ Cortex-M55 PMU
events (see `ns_pmu_map[]` in `ns_pmu_utils.c` for the full list).

## Build & Run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .
nsx view      --app-dir .          # opens SWO viewer
```

## Expected Output

The SWO viewer will print counter dumps every ~2 seconds:

```
--- PMU after 100 iterations ---
  ARM_PMU_CPU_CYCLES        :     614400
  ARM_PMU_INST_RETIRED      :     307200
  ARM_PMU_STALL_FRONTEND    :          0
  ARM_PMU_STALL_BACKEND     :       3072
--- PMU after 100 iterations ---
  ARM_PMU_CPU_CYCLES        :     614400
  ARM_PMU_INST_RETIRED      :     307200
  ARM_PMU_STALL_FRONTEND    :          0
  ARM_PMU_STALL_BACKEND     :       3072
```

The workload is a fixed `256 × i²` accumulation loop repeated 100 times, so
counter values are deterministic across runs.  Frontend stalls are typically
zero (the loop fits in I-cache); backend stalls reflect pipeline data
dependencies.

## How It Works

```c
// Apply a preset — configures 4 event counters
ns_pmu_apply_preset(&g_pmu, NS_PMU_PRESET_BASIC_CPU);
ns_pmu_init(&g_pmu);

// Reset, run workload, read
ns_pmu_reset_counters();
workload();
ns_pmu_get_counters(&g_pmu);
ns_pmu_print_counters(&g_pmu);
```

## Customizing

To switch presets, change the `ns_pmu_apply_preset()` call in `src/main.c`:

```c
ns_pmu_apply_preset(&g_pmu, NS_PMU_PRESET_MEMORY);   // cache & bus events
ns_pmu_apply_preset(&g_pmu, NS_PMU_PRESET_MVE);       // Helium/MVE events
```

Or assign individual events to specific counter slots:

```c
ns_pmu_event_create(&cfg.events[0], 0x0011, NS_PMU_EVENT_COUNTER_SIZE_32); // CPU_CYCLES
ns_pmu_event_create(&cfg.events[1], 0x0039, NS_PMU_EVENT_COUNTER_SIZE_32); // L1D_CACHE_MISS_RD
```
