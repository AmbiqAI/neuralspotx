/*
 * CoreMark platform port for Ambiq NSX — portable score-only build.
 *
 * Timer  : nsx_timer microsecond counter
 * Output : ee_printf -> SEGGER RTT channel 0 (read by J-Link over SWD)
 * Init   : nsx_system_init() — SoC + cache + perf mode
 *
 * Builds across Apollo5 (Cortex-M55) and Apollo4 (Cortex-M4) targets.
 * Power/energy measurement lives in the separate power_benchmark example.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "coremark.h"
#include "core_portme.h"

#include "nsx_system.h"
#include "nsx_timer.h"
#include "am_mcu_apollo.h"
#include "am_util.h"

#include "SEGGER_RTT.h"

#include <stdarg.h>

static const nsx_system_config_t s_coremark_system_config = {
    .perf_mode        = NSX_PERF_HIGH,
    .enable_cache     = true,
    .enable_sram      = true,
    .debug            = { .transport = NSX_DEBUG_ITM },
    .skip_bsp_init    = false,
    .spot_mgr_profile = false,
};

/* ── Volatile seeds (SEED_VOLATILE) ────────────────────────── */
#if VALIDATION_RUN
volatile ee_s32 seed1_volatile = 0x3415;
volatile ee_s32 seed2_volatile = 0x3415;
volatile ee_s32 seed3_volatile = 0x66;
#endif
#if PERFORMANCE_RUN
volatile ee_s32 seed1_volatile = 0x0;
volatile ee_s32 seed2_volatile = 0x0;
volatile ee_s32 seed3_volatile = 0x66;
#endif
#if PROFILE_RUN
volatile ee_s32 seed1_volatile = 0x8;
volatile ee_s32 seed2_volatile = 0x8;
volatile ee_s32 seed3_volatile = 0x8;
#endif
volatile ee_s32 seed4_volatile = ITERATIONS;
volatile ee_s32 seed5_volatile = 0;

/* ── Timer (microsecond) ───────────────────────────────────── */

static nsx_timer_config_t s_timer_cfg = {
    .api = &nsx_timer_V1_0_0,
    .timer = NSX_TIMER_COUNTER,
    .enableInterrupt = false,
};

static CORETIMETYPE start_time_val, stop_time_val;

void
start_time(void)
{
    nsx_timer_clear(&s_timer_cfg);
    start_time_val = nsx_timer_us_read(&s_timer_cfg);
}

void
stop_time(void)
{
    stop_time_val = nsx_timer_us_read(&s_timer_cfg);
}

CORE_TICKS
get_time(void)
{
    return (CORE_TICKS)(stop_time_val - start_time_val);
}

/* Return seconds — timer is in microseconds */
secs_ret
time_in_secs(CORE_TICKS ticks)
{
    return (secs_ret)ticks / (secs_ret)1000000.0;
}

/* ── Contexts ──────────────────────────────────────────────── */
ee_u32 default_num_contexts = 1;

/* ── Platform init/fini ────────────────────────────────────── */
void
portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;

    /* Initialize SEGGER RTT control block early so the J-Link host can
     * locate it as soon as the firmware boots.  NO_BLOCK_TRIM means writes
     * that overflow the 32 KB up-buffer are dropped instead of stalling. */
    SEGGER_RTT_ConfigUpBuffer(0, "CoreMark", NULL, 0,
                              SEGGER_RTT_MODE_NO_BLOCK_TRIM);

    /* Full SoC init: caches, perf mode, debug output */
    nsx_system_init(&s_coremark_system_config);

    /* Start the microsecond timer */
    nsx_timer_init(&s_timer_cfg);

    if (sizeof(ee_ptr_int) != sizeof(ee_u8 *)) {
        ee_printf("ERROR! ee_ptr_int does not hold a pointer!\n");
    }
    if (sizeof(ee_u32) != 4) {
        ee_printf("ERROR! ee_u32 is not 32-bit!\n");
    }

    ee_printf("\n--- CoreMark on Ambiq NSX ---\n");

    p->portable_id = 1;
}

/* ── Platform init/fini ────────────────────────────────────── */
void
portable_fini(core_portable *p)
{
    p->portable_id = 0;

    ee_printf("\n--- CoreMark complete. ---\n");

    /* Spin so the score stays visible on the RTT channel */
    while (1) { __WFI(); }
}

/* ── ee_printf via SEGGER RTT ──────────────────────────────── */
/* RTT writes to an in-SRAM ring buffer that JLinkRTTLogger drains over SWD
 * via background memory reads — no SWO/TPIU pins, no ITM stimulus, and no
 * sensitivity to clock/baud configuration. */
int
ee_printf(const char *fmt, ...)
{
    char    buf[256];
    va_list args;

    va_start(args, fmt);
    int n = am_util_stdio_vsprintf(buf, fmt, args);
    va_end(args);

    if (n > 0) {
        SEGGER_RTT_Write(0, buf, (unsigned)n);
#if defined(NSX_SOC_CORE_M55)
        /* On Cortex-M55 (Apollo5) the J-Link reads the RTT control block +
         * ring buffer over SWD, bypassing the CPU D-cache.  Clean the cache
         * so the host sees the latest WrOff and bytes.  Cortex-M4 targets
         * (Apollo4) have no core D-cache and need no flush. */
        SCB_CleanDCache();
#endif
    }
    return n;
}
