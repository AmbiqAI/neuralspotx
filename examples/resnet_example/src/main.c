#include <stdint.h>
#include <string.h>

#include "nsx_core.h"

#if defined(RESNET_EXAMPLE_HAS_AOT) && defined(RESNET_EXAMPLE_HAS_SAMPLE_DATA)
#include "resnet_model.h"
#include "resnet_sample_data.h"
#endif

#if defined(RESNET_EXAMPLE_HAS_AOT) && defined(RESNET_EXAMPLE_HAS_SAMPLE_DATA)

static int argmax_int8(const int8_t *values, int count)
{
    int best_index = 0;
    int8_t best_value = values[0];

    for (int i = 1; i < count; ++i) {
        if (values[i] > best_value) {
            best_value = values[i];
            best_index = i;
        }
    }

    return best_index;
}

static int max_abs_diff_int8(const int8_t *lhs, const int8_t *rhs, int count)
{
    int max_diff = 0;

    for (int i = 0; i < count; ++i) {
        int diff = (int)lhs[i] - (int)rhs[i];
        if (diff < 0) {
            diff = -diff;
        }
        if (diff > max_diff) {
            max_diff = diff;
        }
    }

    return max_diff;
}

static const int kLogitTolerance = 8;

#endif

int main(void)
{
    nsx_core_config_t cfg = {
        .api = &nsx_core_V1_0_0,
    };
    int32_t status;

    status = nsx_core_init(&cfg);
    if (status != NSX_STATUS_SUCCESS) {
        return (int)status;
    }

    nsx_itm_printf_enable();
    nsx_printf("resnet_example: initializing AOT model\r\n");

#if !defined(RESNET_EXAMPLE_HAS_AOT) || !defined(RESNET_EXAMPLE_HAS_SAMPLE_DATA)
    nsx_printf("tutorial scaffold is incomplete\r\n");
#if !defined(RESNET_EXAMPLE_HAS_AOT)
    nsx_printf("missing generated module: modules/resnet-aot/\r\n");
#endif
#if !defined(RESNET_EXAMPLE_HAS_SAMPLE_DATA)
    nsx_printf("missing generated sample data: src/resnet_sample_data.h\r\n");
#endif
    nsx_printf("download the Ambiq model-zoo artifacts and follow README.md\r\n");
    while (1) {
        nsx_delay_us(1000000);
    }
#else
    resnet_model_context_t model_ctx = {0};

    status = resnet_model_init(&model_ctx);
    if (status != resnet_status_ok) {
        nsx_printf("resnet_model_init failed: %ld\r\n", (long)status);
        return (int)status;
    }

    if (model_ctx.inputs[0].size != RESNET_GOLDEN_INPUT_SIZE) {
        nsx_printf("unexpected input size: %u\r\n", (unsigned)model_ctx.inputs[0].size);
        return 1;
    }
    if (model_ctx.outputs[0].size != RESNET_GOLDEN_OUTPUT_SIZE) {
        nsx_printf("unexpected output size: %u\r\n", (unsigned)model_ctx.outputs[0].size);
        return 1;
    }

    memcpy(model_ctx.inputs[0].data, kResnetGoldenInput, RESNET_GOLDEN_INPUT_SIZE);

    status = resnet_model_run(&model_ctx);
    if (status != resnet_status_ok) {
        nsx_printf("resnet_model_run failed: %ld\r\n", (long)status);
        return (int)status;
    }

    {
        const int8_t *scores = model_ctx.outputs[0].data;
        const int output_len = (int)model_ctx.outputs[0].size;
        const int best_index = argmax_int8(scores, output_len);
        const int classification_match = (best_index == RESNET_GOLDEN_EXPECTED_INDEX);
        const int max_abs_diff = max_abs_diff_int8(
            scores, kResnetGoldenOutput, RESNET_GOLDEN_OUTPUT_SIZE);
        const int tolerance_match = (max_abs_diff <= kLogitTolerance);

        nsx_printf("input bytes: %u\r\n", (unsigned)model_ctx.inputs[0].size);
        nsx_printf("output bytes: %u\r\n", (unsigned)model_ctx.outputs[0].size);
        nsx_printf("expected class index: %d (%s)\r\n",
                   RESNET_GOLDEN_EXPECTED_INDEX,
                   kResnetLabels[RESNET_GOLDEN_EXPECTED_INDEX]);
        nsx_printf("predicted class index: %d (%s)\r\n",
                   best_index,
                   kResnetLabels[best_index]);
        nsx_printf("scores:");
        for (int i = 0; i < output_len; ++i) {
            nsx_printf(" %d", scores[i]);
        }
        nsx_printf("\r\n");
        nsx_printf("classification match: %s\r\n", classification_match ? "PASS" : "FAIL");
        nsx_printf("max logit diff vs golden: %d\r\n", max_abs_diff);
        nsx_printf("logit tolerance match (+/-%d): %s\r\n",
                   kLogitTolerance,
                   tolerance_match ? "PASS" : "FAIL");
    }

    while (1) {
        nsx_delay_us(1000000);
    }
#endif
}
