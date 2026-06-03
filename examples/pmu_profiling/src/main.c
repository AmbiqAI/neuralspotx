#include <stdint.h>
#include "ns_core.h"
#include "am_mcu_apollo.h"
#include "am_util_pmu.h"

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
    ns_core_config_t core_cfg = {
        .api = &ns_core_V1_0_0,
    };
    (void)ns_core_init(&core_cfg);

    nsx_itm_printf_enable();

    am_util_pmu_config_t pmu_cfg = {0};
    am_util_pmu_profiling_t profiling = {0};

    pmu_cfg.ui32Counters = PMU_CNTENSET_CNT0_ENABLE_Msk |
                           PMU_CNTENSET_CCNTR_ENABLE_Msk;
    pmu_cfg.ui32EventType[0] = ARM_PMU_INST_RETIRED;

    am_util_pmu_enable();
    am_util_pmu_init(&pmu_cfg);

    while (1) {
        ARM_PMU_CYCCNT_Reset();
        ARM_PMU_EVCNTR_ALL_Reset();

        for (uint32_t n = 0; n < OUTER_LOOPS; ++n) {
            workload();
        }

        nsx_printf("--- PMU after %u iterations ---\r\n", (unsigned)OUTER_LOOPS);
        am_util_pmu_get_profiling(&pmu_cfg, &profiling);
        nsx_printf("cycles=%lu instructions=%lu\r\n",
                   (unsigned long)profiling.cycleProfiling.ui32CountValue,
                   (unsigned long)profiling.eventProfiling[0].ui32CountValue);
        nsx_delay_us(2000000);
    }
}
