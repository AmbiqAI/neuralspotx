# pmu_profiling

Demonstrates the **nsx-pmu-armv8m** module on the Apollo510 EVB. Configures
the Arm Cortex-M55 Performance Monitoring Unit (PMU) to track CPU cycles and
retired instructions for a tight integer workload, printing a minimal summary
over SWO every 2 seconds.

## What is the PMU?

The Cortex-M55 has a hardware PMU with 8 configurable event counters plus a
dedicated cycle counter. Each counter can be assigned to any of ~70 hardware
events (cache misses, stalls, MVE instructions, bus accesses, etc.). The
standalone **nsx-pmu-armv8m** module provides the shared PMU API, while the
selected SDK supplies the local `nsx_ambiq_pmu` backend shim.

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

The SWO viewer will print a compact PMU summary every ~2 seconds:

```
--- PMU after 100 iterations ---
cycles=230563 inst=130093
--- PMU after 100 iterations ---
cycles=230563 inst=130093
```

The workload is a fixed `256 × i²` accumulation loop repeated 100 times, so
counter values are usually stable across runs. Occasional small outliers are
expected from normal runtime noise such as interrupts or SWO activity.

## How It Works

```c
// Configure the two counters this example prints
g_pmu.api = &nsx_pmu_V1_0_0;
nsx_pmu_reset_config(&g_pmu);
nsx_pmu_event_create(&g_pmu.events[0], ARM_PMU_CPU_CYCLES, NSX_PMU_EVENT_COUNTER_SIZE_32);
nsx_pmu_event_create(&g_pmu.events[1], ARM_PMU_INST_RETIRED, NSX_PMU_EVENT_COUNTER_SIZE_32);
nsx_pmu_init(&g_pmu);

// Reset, run workload, read
nsx_pmu_reset_counters();
workload();
nsx_pmu_get_counters(&g_pmu);
nsx_printf("cycles=%lu inst=%lu\r\n",
           (unsigned long)g_pmu.counter[0].counterValue,
           (unsigned long)g_pmu.counter[1].counterValue);
```

## Customizing

To profile different events, change the two `nsx_pmu_event_create()` calls in
`src/main.c`:

```c
nsx_pmu_event_create(&cfg.events[0], 0x0011, NSX_PMU_EVENT_COUNTER_SIZE_32); // CPU_CYCLES
nsx_pmu_event_create(&cfg.events[1], 0x0039, NSX_PMU_EVENT_COUNTER_SIZE_32); // L1D_CACHE_MISS_RD
```
