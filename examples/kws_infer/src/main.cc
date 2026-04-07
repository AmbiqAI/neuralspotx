/**
 * @file main.cc
 * @brief KWS inference demo using HeliaRT on Apollo510.
 *
 * Loads a keyword-spotting TFLite model (embedded as a C array),
 * runs a single inference with dummy input, and prints the results
 * over SWO / UART.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>

// TFLM / HeliaRT headers
#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/micro/tflite_bridge/micro_error_reporter.h"
#include "tensorflow/lite/schema/schema_generated.h"

// Per-layer PMU profiler
#include "nsx_pmu_profiler.h"

// NSX runtime
extern "C" {
#include "ns_core.h"
#include "ns_ambiqsuite_harness.h"
#include "nsx_mem.h"
#include "nsx_system.h"
}

// DWT cycle counter helpers (Cortex-M55)
static inline void dwt_init(void) {
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}
static inline uint32_t dwt_cycles(void) { return DWT->CYCCNT; }

// Embedded model
#include "kws_model_data.h"

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

// KWS model: input [1,49,10,1] int8, output [1,12] int8
// Ops: Conv2D, DepthwiseConv2D, AveragePool2D, FullyConnected, Reshape, Softmax
static constexpr int kNumOps    = 6;
static constexpr int kArenaSize = 64 * 1024;  // 64 KB tensor arena

// KWS class labels (Google Speech Commands subset, 12 classes)
static const char *kLabels[] = {
    "silence", "unknown", "yes", "no", "up", "down",
    "left", "right", "on", "off", "stop", "go"
};
static constexpr int kNumClasses = 12;

/* ------------------------------------------------------------------ */
/* Globals                                                             */
/* ------------------------------------------------------------------ */

// Tensor arena — uninit, in fast TCM for 0-wait access during inference
NSX_MEM_FAST_BSS alignas(16) static uint8_t g_arena[kArenaSize];

// Per-layer PMU profiler (global so it survives across inference calls)
static NsxPmuProfiler g_profiler;

/* ------------------------------------------------------------------ */
/* Op resolver — only register what the model needs                    */
/* ------------------------------------------------------------------ */

static tflite::MicroMutableOpResolver<kNumOps> &get_resolver() {
    static tflite::MicroMutableOpResolver<kNumOps> resolver;
    static bool initialized = false;
    if (!initialized) {
        resolver.AddConv2D();
        resolver.AddDepthwiseConv2D();
        resolver.AddAveragePool2D();
        resolver.AddFullyConnected();
        resolver.AddReshape();
        resolver.AddSoftmax();
        initialized = true;
    }
    return resolver;
}

/* ------------------------------------------------------------------ */
/* Main                                                                */
/* ------------------------------------------------------------------ */

int main(void) {
    // --- NSX system init: HP mode, caches, ITM/SWO, SpotManager ---
    // Uses minimal HW init (skips BSP's 2-second delay) with ITM debug.
    nsx_system_config_t sys_cfg = nsx_system_development;
    sys_cfg.skip_bsp_init = true;  // fast startup, no BSP delay
    NS_TRY(nsx_system_init(&sys_cfg), "System init failed\n");

    dwt_init();

    ns_printf("KWS Inference Demo (HeliaRT)\n");
    ns_printf("Model size: %u bytes\n", kws_model_data_len);

    // --- TFLM setup ---
    tflite::InitializeTarget();

    const tflite::Model *model = tflite::GetModel(kws_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        ns_printf("ERROR: Model schema version %lu != expected %d\n",
                  model->version(), TFLITE_SCHEMA_VERSION);
        while (1) {}
    }

    tflite::MicroMutableOpResolver<kNumOps> &resolver = get_resolver();

    // Init PMU profiler with ML-default counters
    g_profiler.Init(NS_PMU_PRESET_ML_DEFAULT);

    tflite::MicroInterpreter interpreter(model, resolver, g_arena, kArenaSize,
                                         nullptr, &g_profiler);

    TfLiteStatus status = interpreter.AllocateTensors();
    if (status != kTfLiteOk) {
        ns_printf("ERROR: AllocateTensors() failed\n");
        while (1) {}
    }

    // Report arena usage
    size_t used = interpreter.arena_used_bytes();
    ns_printf("Arena: %u / %u bytes used (%.1f%%)\n",
              (unsigned)used, kArenaSize, 100.0f * used / kArenaSize);

    TfLiteTensor *input  = interpreter.input(0);
    TfLiteTensor *output = interpreter.output(0);

    ns_printf("Input:  dims=[%d,%d,%d,%d] type=%d\n",
              input->dims->data[0], input->dims->data[1],
              input->dims->data[2], input->dims->data[3],
              input->type);
    ns_printf("Output: dims=[%d,%d] type=%d\n",
              output->dims->data[0], output->dims->data[1],
              output->type);

    // --- Fill input with dummy data (zeros = silence) ---
    memset(input->data.int8, 0, input->bytes);

    // --- Run inference ---
    ns_printf("Running inference...\n");

    uint32_t start_cyc = dwt_cycles();
    status = interpreter.Invoke();
    uint32_t end_cyc = dwt_cycles();

    if (status != kTfLiteOk) {
        ns_printf("ERROR: Invoke() failed\n");
        while (1) {}
    }

    // CPU runs at ~96 MHz
    uint32_t elapsed_us = (end_cyc - start_cyc) / 96;
    ns_printf("Inference time: %lu us (%lu cycles)\n",
              (unsigned long)elapsed_us, (unsigned long)(end_cyc - start_cyc));

    // --- Per-layer PMU stats ---
    ns_printf("\n--- Per-Layer PMU Profile ---\n");
    g_profiler.PrintCsv();
    g_profiler.ClearEvents();

    // --- Print output scores ---
    ns_printf("\n--- Results ---\n");
    int8_t best_score = -128;
    int    best_idx   = 0;
    for (int i = 0; i < kNumClasses && i < output->dims->data[1]; i++) {
        int8_t score = output->data.int8[i];
        ns_printf("  [%2d] %-10s  score=%4d\n", i, kLabels[i], (int)score);
        if (score > best_score) {
            best_score = score;
            best_idx   = i;
        }
    }
    ns_printf("\nPrediction: \"%s\" (score=%d)\n", kLabels[best_idx], (int)best_score);

    // --- Loop forever (re-run every ~2 seconds using DWT busy-wait) ---
    while (1) {
        // DWT-based delay: ~2 seconds at 96 MHz
        {
            uint32_t t0 = dwt_cycles();
            while ((dwt_cycles() - t0) < (96000000u * 2)) {}
        }

        // Fill with random-ish pattern to exercise more of the model
        for (size_t i = 0; i < input->bytes; i++) {
            input->data.int8[i] = (int8_t)((i * 37 + 13) & 0xFF);
        }

        start_cyc = dwt_cycles();
        interpreter.Invoke();
        end_cyc = dwt_cycles();
        elapsed_us = (end_cyc - start_cyc) / 96;

        // Print per-layer PMU for this inference
        g_profiler.PrintCsv();
        g_profiler.ClearEvents();

        best_score = -128;
        best_idx   = 0;
        for (int i = 0; i < kNumClasses && i < output->dims->data[1]; i++) {
            int8_t score = output->data.int8[i];
            if (score > best_score) {
                best_score = score;
                best_idx   = i;
            }
        }
        ns_printf("Inference: %lu us -> \"%s\" (score=%d)\n",
                  (unsigned long)elapsed_us, kLabels[best_idx], (int)best_score);
    }

    return 0;
}
