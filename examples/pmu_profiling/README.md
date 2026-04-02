# pmu_profiling

Demonstrates **nsx-pmu-armv8m** on the Apollo510 EVB.  Uses the PMU
cycle counter to measure a simple integer workload and reports
elapsed cycles over SWO.

## Build & run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .
nsx view      --app-dir .
```
