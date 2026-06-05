/**
 * @file nsx_pmu_profiler.cc
 * @brief PMU-backed per-layer profiler for TFLM inference.
 */

#include "nsx_pmu_profiler.h"

#include "am_mcu_apollo.h"
#include "ns_core.h"
#include "nsx_pmu_map.h"

void NsxPmuProfiler::Init(nsx_pmu_preset_e preset) {
    nsx_pmu_reset_config(&pmu_cfg_);
    pmu_cfg_.api = &nsx_pmu_V1_0_0;
    nsx_pmu_apply_preset(&pmu_cfg_, preset);
    nsx_pmu_init(&pmu_cfg_);
    num_events_ = 0;
    initialized_ = true;
}

uint32_t NsxPmuProfiler::BeginEvent(const char* tag) {
    if (!initialized_ || num_events_ >= kMaxLayers) {
        return 0;
    }
    int idx = num_events_++;
    layers_[idx].tag = tag;
    // Reset event counters but preserve DWT CYCCNT (which is an alias
    // of PMU CCNTR on Cortex-M55 - nsx_pmu_reset_counters would zero it).
    uint32_t saved_cyccnt = DWT->CYCCNT;
    nsx_pmu_reset_counters();
    DWT->CYCCNT = saved_cyccnt;
    return static_cast<uint32_t>(idx);
}

void NsxPmuProfiler::EndEvent(uint32_t event_handle) {
    if (!initialized_ || event_handle >= static_cast<uint32_t>(num_events_)) {
        return;
    }
    // Snapshot the counters (nsx_pmu_get_counters also resets internally,
    // so preserve DWT CYCCNT here too).
    uint32_t saved_cyccnt = DWT->CYCCNT;
    nsx_pmu_get_counters(&pmu_cfg_);
    DWT->CYCCNT = saved_cyccnt;
    LayerRecord& rec = layers_[event_handle];
    for (int i = 0; i < kNumEvents; i++) {
        rec.counters[i] = pmu_cfg_.counter[i].counterValue;
    }
}

void NsxPmuProfiler::ClearEvents() {
    num_events_ = 0;
}

void NsxPmuProfiler::PrintCsv() const {
    if (!initialized_ || num_events_ == 0) {
        return;
    }

    // Build header from event names
    nsx_printf("\"Layer\",\"Op\"");
    for (int e = 0; e < kNumEvents; e++) {
        if (!pmu_cfg_.events[e].enabled) break;
        // Look up the name from the PMU map via the counter's map index
        uint32_t map_idx = pmu_cfg_.counter[e].mapIndex;
        if (map_idx < NSX_PMU_MAP_SIZE) {
            nsx_printf(",\"%s\"", nsx_pmu_map[map_idx].regname);
        } else {
            nsx_printf(",\"event_%d\"", e);
        }
    }
    nsx_printf("\n");

    // One row per layer
    for (int i = 0; i < num_events_; i++) {
        const LayerRecord& rec = layers_[i];
        nsx_printf("%d,%s", i, rec.tag ? rec.tag : "?");
        for (int e = 0; e < kNumEvents; e++) {
            if (!pmu_cfg_.events[e].enabled) break;
            nsx_printf(",%lu", (unsigned long)rec.counters[e]);
        }
        nsx_printf("\n");
    }
}
