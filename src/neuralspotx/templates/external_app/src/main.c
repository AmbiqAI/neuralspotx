#include "ns_core.h"
#include "ns_ambiqsuite_harness.h"

int main(void)
{
    ns_core_config_t cfg = {
        .api = &ns_core_V1_0_0,
    };
    (void)ns_core_init(&cfg);

    ns_itm_printf_enable();

    while (1) {
        ns_printf("nsx hello from generated app\r\n");
        ns_delay_us(1000000);
    }
}
