#include "nsx_core.h"

int main(void)
{
    nsx_core_config_t cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&cfg);

    nsx_itm_printf_enable();

    while (1) {
        nsx_printf("Hello from nsx!\r\n");
        nsx_delay_us(1000000);
    }
}
