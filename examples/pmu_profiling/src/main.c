#include <stdint.h>
#include "nsx_core.h"
#include "am_mcu_apollo.h"
#include "nsx_pmu_utils.h"

#define VECTOR_LEN  256
#define OUTER_LOOPS 100

static volatile int32_t g_sink;

static void workload(void)
{
    volatile int32_t acc = 0;
    for (uint32_t i = 0; i < VECTOR_LEN; ++i) {
        acc += (int32_t)(i * i);
    }
    g_sink = acc;
}

int main(void)
{
    nsx_core_config_t core_cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&core_cfg);

    nsx_itm_printf_enable();

    nsx_pmu_config_t pmu_cfg = {0};
    nsx_pmu_apply_preset(&pmu_cfg, NSX_PMU_PRESET_BASIC_CPU);
    pmu_cfg.api = &nsx_pmu_V1_0_0;

    if (nsx_pmu_init(&pmu_cfg) != NSX_STATUS_SUCCESS) {
        nsx_printf("PMU init failed\r\n");
        while (1) {
        }
    }

    while (1) {
        nsx_pmu_reset_counters();

        for (uint32_t n = 0; n < OUTER_LOOPS; ++n) {
            workload();
        }

        nsx_printf("--- PMU after %u iterations ---\r\n", (unsigned)OUTER_LOOPS);
        if (nsx_pmu_get_counters(&pmu_cfg) == NSX_STATUS_SUCCESS) {
            nsx_printf("cycles=%lu inst=%lu\r\n",
                       (unsigned long)pmu_cfg.counter[0].counterValue,
                       (unsigned long)pmu_cfg.counter[1].counterValue);
        } else {
            nsx_printf("PMU read failed\r\n");
        }
        nsx_delay_us(2000000);
    }
}
