/* SPDX-License-Identifier: BSD-3-Clause */
#include "nsx_core.h"
#include "pilot.h"

int pilot_console_init(void) {
    nsx_core_config_t config = {.api = &nsx_core_V1_0_0};
    if (nsx_core_init(&config) != 0) {
        return 1;
    }
    nsx_itm_printf_enable();
    return 0;
}

void pilot_putchar(int ch) {
    nsx_printf("%c", ch);
}
