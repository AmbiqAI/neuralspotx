/* SPDX-License-Identifier: BSD-3-Clause */
/* Copyright (c) 2026, Ambiq */
/*
 * Small secondary firmware image for exercising named-target flashing.
 * It intentionally avoids the BLE/FreeRTOS application policy in main.c.
 */
#include "nsx_core.h"

int main(void)
{
    nsx_core_config_t cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&cfg);

    nsx_itm_printf_enable();

    while (1) {
        nsx_printf("ble_webble_flash_probe: named-target image running\r\n");
        nsx_delay_us(1000000);
    }
}
