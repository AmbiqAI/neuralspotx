/**
 * @file nsx_pmu_profiler.h
 * @brief Per-layer PMU profiler for TFLM (HeliaRT).
 *
 * Implements MicroProfilerInterface to capture hardware PMU counters
 * around each operator invocation during inference. After Invoke(),
 * call PrintCsv() to dump per-layer results over ITM/UART.
 *
 * Uses nsx-pmu-armv8m: 4 events × 32-bit counters per pass.
 */

#ifndef NSX_PMU_PROFILER_H
#define NSX_PMU_PROFILER_H

#include "tensorflow/lite/micro/micro_profiler_interface.h"

extern "C" {
#include "ns_pmu_utils.h"
}

class NsxPmuProfiler : public tflite::MicroProfilerInterface {
 public:
    static constexpr int kMaxLayers = 128;
    // 4 events at 32-bit width = 8 HW counters (chained pairs)
    static constexpr int kNumEvents = 4;

    NsxPmuProfiler() = default;
    ~NsxPmuProfiler() override = default;

    /// Initialise PMU hardware with a preset. Call once before Invoke().
    void Init(ns_pmu_preset_e preset = NS_PMU_PRESET_ML_DEFAULT);

    /// MicroProfilerInterface hooks — called by TFLM per operator.
    uint32_t BeginEvent(const char* tag) override;
    void EndEvent(uint32_t event_handle) override;

    /// Reset recorded data for next inference.
    void ClearEvents();

    /// Print CSV header + one row per layer to ns_printf.
    void PrintCsv() const;

    int num_events() const { return num_events_; }

 private:
    struct LayerRecord {
        const char* tag;
        uint32_t counters[kNumEvents];
    };

    ns_pmu_config_t pmu_cfg_ = {};
    LayerRecord layers_[kMaxLayers] = {};
    int num_events_ = 0;
    bool initialized_ = false;
};

#endif // NSX_PMU_PROFILER_H
