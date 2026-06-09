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
    pmu_cfg.api = &nsx_pmu_V1_0_0;
    nsx_pmu_reset_config(&pmu_cfg);
    nsx_pmu_event_create(&pmu_cfg.events[0], ARM_PMU_CPU_CYCLES, NSX_PMU_EVENT_COUNTER_SIZE_32);
    nsx_pmu_event_create(&pmu_cfg.events[1], ARM_PMU_INST_RETIRED, NSX_PMU_EVENT_COUNTER_SIZE_32);

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
