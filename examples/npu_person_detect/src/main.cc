/**
 * @file main.cc
 * @brief person_detect TFLite Micro inference on the atomiq110 Ethos-U85 NPU.
 *
 * Runs the Vela-compiled int8 person-detection model (100% NPU offload —
 * the whole graph is a single `ethos-u` custom op) with generated test
 * inputs and prints scores + timing over ITM/SWO.
 *
 * The NPU is powered and the Ethos-U core driver initialized through the
 * nsx-npu module; heliaRT's ethos-u custom-op kernel (enabled with
 * NSX_HELIA_RT_ENABLE_ETHOSU) dispatches the command stream to the driver.
 */

#include <cstdint>
#include <cstdio>
#include <cstring>

#include "am_mcu_apollo.h"

#include "tensorflow/lite/micro/micro_interpreter.h"
#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"
#include "tensorflow/lite/micro/system_setup.h"
#include "tensorflow/lite/schema/schema_generated.h"

#include "nsx_core.h"
#include "nsx_npu.h"

#include "person_detect_model_data.h"
#include "test_inputs.h"

static inline void dwt_init(void) {
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}
static inline uint32_t dwt_cycles(void) { return DWT->CYCCNT; }

// atomiq110 FPGA turbo core clock (48 MHz)
static constexpr uint32_t kCpuHz = 48000000u;

// Vela-compiled person_detect: input [1,96,96,1] int8, output [1,2] int8.
// The graph is one ethos-u custom op; the CPU kernels below are only used
// if the model is re-compiled by Vela with partial offload.
static constexpr int kNumOps    = 6;
static constexpr int kArenaSize = 512 * 1024;

static const char *kLabels[] = { "no-person", "person" };

// Arena lives in SHARED_SRAM (.shared, NOLOAD): the Ethos-U85 is a bus
// master and cannot access the core-private TCM, and the arena is far too
// large for it anyway. TFLM does not require a zeroed arena.
__attribute__((section(".shared"), aligned(16)))
static uint8_t g_arena[kArenaSize];

static tflite::MicroMutableOpResolver<kNumOps> &get_resolver() {
    static tflite::MicroMutableOpResolver<kNumOps> resolver;
    static bool initialized = false;
    if (!initialized) {
        resolver.AddEthosU();
        resolver.AddConv2D();
        resolver.AddDepthwiseConv2D();
        resolver.AddAveragePool2D();
        resolver.AddReshape();
        resolver.AddSoftmax();
        initialized = true;
    }
    return resolver;
}

static void run_case(tflite::MicroInterpreter &interp, const char *name,
                     const int8_t *data, size_t len) {
    TfLiteTensor *input  = interp.input(0);
    TfLiteTensor *output = interp.output(0);

    if (len > input->bytes) len = input->bytes;
    memcpy(input->data.int8, data, len);

    uint32_t t0 = dwt_cycles();
    TfLiteStatus status = interp.Invoke();
    uint32_t dt = dwt_cycles() - t0;

    if (status != kTfLiteOk) {
        nsx_printf("[%s] ERROR: Invoke() failed\n", name);
        return;
    }

    uint32_t ms = dt / (kCpuHz / 1000u);
    nsx_printf("[%-8s] %lu ms (%lu cycles)  ", name,
               (unsigned long)ms, (unsigned long)dt);
    for (int i = 0; i < output->dims->data[1]; i++) {
        nsx_printf("%s=%d ", kLabels[i], (int)output->data.int8[i]);
    }
    int8_t s0 = output->data.int8[0], s1 = output->data.int8[1];
    nsx_printf("-> %s\n", (s1 > s0) ? kLabels[1] : kLabels[0]);
}

int main(void) {
    nsx_core_config_t cfg{};
    cfg.api = &nsx_core_V1_0_0;
    (void)nsx_core_init(&cfg);
    nsx_itm_printf_enable();
    dwt_init();

    nsx_printf("\nperson_detect on atomiq110 Ethos-U85 (TFLM + Vela)\n");
    nsx_printf("Model: %u bytes (ethos-u85-256, 100%% NPU offload)\n",
               g_person_detect_model_data_len);

    // perf_mode: HP works on both silicon and the NPU-enabled FPGA image
    // (hardware-validated); set skip_perf_mode = true only if mode_select
    // must be bypassed on a custom pre-silicon target.
    nsx_npu_config_t npu_cfg{};
    npu_cfg.perf_mode      = NSX_NPU_PERF_HIGH_PERFORMANCE;
    npu_cfg.skip_perf_mode = false;
    uint32_t npu_rc = nsx_npu_init(&npu_cfg);
    if (npu_rc != 0) {
        // Keep repeating so the message is visible whenever a viewer attaches.
        while (1) {
            nsx_printf("ERROR: nsx_npu_init failed (rc=%lu).\n",
                       (unsigned long)npu_rc);
            nsx_printf("Ethos-U85 init failed. On FPGA builds make sure the "
                       "loaded bitstream generation matches the SDK payload "
                       "and includes a working Ethos-U85; otherwise run the "
                       "CPU person_detect variant instead.\n");
            nsx_delay_us(5000000);
        }
    }
    nsx_printf("Ethos-U85 driver initialized.\n");

    tflite::InitializeTarget();

    const tflite::Model *model = tflite::GetModel(g_person_detect_model_data);
    if (model->version() != TFLITE_SCHEMA_VERSION) {
        nsx_printf("ERROR: schema %lu != %d\n",
                   (unsigned long)model->version(), TFLITE_SCHEMA_VERSION);
        while (1) {}
    }

    tflite::MicroInterpreter interpreter(model, get_resolver(), g_arena,
                                         kArenaSize);
    if (interpreter.AllocateTensors() != kTfLiteOk) {
        nsx_printf("ERROR: AllocateTensors() failed\n");
        while (1) {}
    }
    nsx_printf("Arena: %u / %u bytes\n",
               (unsigned)interpreter.arena_used_bytes(), kArenaSize);

    TfLiteTensor *input = interpreter.input(0);
    nsx_printf("Input: [%d,%d,%d,%d] int8, %u bytes\n\n",
               input->dims->data[0], input->dims->data[1],
               input->dims->data[2], input->dims->data[3],
               (unsigned)input->bytes);

    while (1) {
        memset(input->data.int8, 0, input->bytes);
        run_case(interpreter, "zeros", input->data.int8, 0);
        run_case(interpreter, "noise", g_test_input_noise,
                 sizeof(g_test_input_noise));
        run_case(interpreter, "gradient", g_test_input_gradient,
                 sizeof(g_test_input_gradient));
        nsx_printf("---\n");
        nsx_delay_us(3000000);
    }
}
