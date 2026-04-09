/**
 * @file core_portme.c
 * @brief CoreMark platform port for Ambiq NSX (power_benchmark)
 *
 * Minimal port: timer, seeds, printf.  Power management is handled
 * entirely by main.c — portable_fini() just prints results and
 * stashes the results pointer for the ITCM measurement loop.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "coremark.h"
#include "core_portme.h"

#include "nsx_system.h"
#include "ns_timer.h"
#include "ns_ambiqsuite_harness.h"

#include <stdarg.h>
#include <stddef.h>

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

static ns_timer_config_t s_timer_cfg = {
    .api = &ns_timer_V1_0_0,
    .timer = NS_TIMER_COUNTER,
    .enableInterrupt = false,
};

static CORETIMETYPE start_time_val, stop_time_val;

void
start_time(void)
{
    ns_timer_clear(&s_timer_cfg);
    start_time_val = ns_us_ticker_read(&s_timer_cfg);
}

void
stop_time(void)
{
    stop_time_val = ns_us_ticker_read(&s_timer_cfg);
}

CORE_TICKS
get_time(void)
{
    return (CORE_TICKS)(stop_time_val - start_time_val);
}

secs_ret
time_in_secs(CORE_TICKS ticks)
{
    return (secs_ret)ticks / (secs_ret)1000000.0;
}

/* ── Contexts ──────────────────────────────────────────────── */
ee_u32 default_num_contexts = 1;

/* ── Results pointer for ITCM loop ─────────────────────────── */
extern void *s_coremark_results;  /* defined in main.c */

/* ── Platform init/fini ────────────────────────────────────── */
void
portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;

    /* Timer is our only platform dependency */
    ns_timer_init(&s_timer_cfg);

    if (sizeof(ee_ptr_int) != sizeof(ee_u8 *)) {
        ee_printf("ERROR! ee_ptr_int does not hold a pointer!\n");
    }
    if (sizeof(ee_u32) != 4) {
        ee_printf("ERROR! ee_u32 is not 32-bit!\n");
    }

    ee_printf("--- CoreMark on Ambiq NSX ---\n");
    p->portable_id = 1;
}

void
portable_fini(core_portable *p)
{
    p->portable_id = 0;

    /* Stash the core_results pointer for iterate() in the ITCM loop.
     * core_portable is the last member of core_results. */
    s_coremark_results = (void *)((char *)p - offsetof(core_results, port));

    ee_printf("--- CoreMark complete ---\n");
}

/* ── ee_printf via ITM/SWO ─────────────────────────────────── */
int
ee_printf(const char *fmt, ...)
{
    char    buf[256];
    va_list args;

    va_start(args, fmt);
    int n = am_util_stdio_vsprintf(buf, fmt, args);
    va_end(args);

    ns_printf("%s", buf);
    return n;
}
