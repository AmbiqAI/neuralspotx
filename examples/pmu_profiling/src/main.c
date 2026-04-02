#include <stdint.h>
#include "ns_core.h"
#include "ns_ambiqsuite_harness.h"
#include "ns_pmu_utils.h"

#define VECTOR_LEN  256
#define OUTER_LOOPS 100

static volatile int32_t g_sink;
static ns_pmu_config_t g_pmu;

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

    ns_itm_printf_enable();

    /* Configure the PMU with the basic CPU preset (cycles, instructions, etc). */
    g_pmu.api = &ns_pmu_V1_0_0;
    ns_pmu_apply_preset(&g_pmu, NS_PMU_PRESET_BASIC_CPU);
    ns_pmu_init(&g_pmu);

    while (1) {
        ns_pmu_reset_counters();

        for (uint32_t n = 0; n < OUTER_LOOPS; ++n) {
            workload();
        }

        ns_pmu_get_counters(&g_pmu);
        ns_printf("--- PMU after %u iterations ---\r\n", (unsigned)OUTER_LOOPS);
        ns_pmu_print_counters(&g_pmu);
        ns_delay_us(2000000);
    }
}
