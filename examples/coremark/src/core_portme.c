/*
 * CoreMark platform port for Ambiq NSX
 *
 * Timer     : ns_us_ticker_read() — microsecond resolution
 * Output    : am_util_stdio_printf (ITM/SWO)
 * Init      : nsx_system_init() — full SoC + debug + perf mode
 *
 * After results are printed, SWO is disabled and the benchmark
 * alternates between 30s compute (for active power) and 30s deep
 * sleep (for sleep power) so both can be measured on a Joulescope.
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "coremark.h"
#include "core_portme.h"

#include "nsx_system.h"
#include "nsx_power.h"
#include "ns_timer.h"
#include "ns_ambiqsuite_harness.h"
#include "ns_energy_monitor.h"

#include "SEGGER_RTT.h"

#include <stdarg.h>

/*
 * ITCM-resident trampoline: shuts off NVM (MRAM) and caches, then
 * enters the infinite CoreMark iterate() loop.  Once NVM is off,
 * NO code in MRAM can execute — everything must be in ITCM/DTCM.
 * iterate() only calls core_bench_list and crcu16, both in ITCM via
 * the linker script.
 */
__attribute__((section(".itcm_text"), noinline, noreturn))
static void
itcm_power_loop(void *results)
{
    /* Power off NVM — we're running from ITCM, no MRAM access needed.
     * portable_fini() already zeroed DEVPWREN, AUDSSPWREN, SSRAMPWREN,
     * SSRAMRETCFG via HAL calls.  NVM must be the LAST peripheral turned
     * off to avoid hardware interlocks that re-enable it. */
    PWRCTRL->MEMPWREN_b.PWRENNVM  = 0;
    PWRCTRL->MEMPWREN_b.PWRENNVM1 = 0;
    __DSB();
    __ISB();

    /* Disable caches — ITCM/DTCM are zero-wait-state, caches waste power.
     * Also required: without this, NVM power-down doesn't finalize. */
    SCB->ICIALLU = 0;   /* Invalidate I-cache */
    __DSB();
    __ISB();
    SCB->CCR &= ~SCB_CCR_IC_Msk;  /* Disable I-cache */
    SCB->CCR &= ~SCB_CCR_DC_Msk;  /* Disable D-cache */
    __DSB();
    __ISB();

    /* Signal ACTIVE to Joulescope via GPIO (register-write macros, no HAL call) */
    /* GPIO29 = bit0 HIGH, GPIO36 = bit1 LOW → NS_DATA_COLLECTION pattern */
    am_hal_gpio_output_set(NS_POWER_MONITOR_GPIO_0);
    am_hal_gpio_output_clear(NS_POWER_MONITOR_GPIO_1);

    /* Drain the NVM read pipeline.  After clearing PWRENNVM, the NVM
     * controller waits for outstanding MRAM fetches to complete before
     * committing to power-down.  If the compiler inlines all library
     * calls (memset, etc.) into ITCM — as armclang -Ofast does — no
     * MRAM bus transactions occur and NVM never powers off (~1.4 mA
     * penalty).  A single volatile read from the MRAM address space
     * forces one bus cycle that lets the NVM controller settle. */
    {
        volatile ee_u32 dummy = *(volatile ee_u32 *)0x00430000;
        (void)dummy;
    }

    while (1) {
        iterate(results);
    }
}

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

/* Return seconds — timer is in microseconds */
secs_ret
time_in_secs(CORE_TICKS ticks)
{
    return (secs_ret)ticks / (secs_ret)1000000.0;
}

/* ── Contexts ──────────────────────────────────────────────── */
ee_u32 default_num_contexts = 1;

/*
 * Stash the core_results pointer so portable_fini() can re-run
 * iterate() in a tight loop for power measurement.  portable_init
 * receives &results[0].port which sits at the end of core_results.
 */
#include <stddef.h>
static void *s_results_ptr = NULL;

/* ── Platform init/fini ────────────────────────────────────── */
void
portable_init(core_portable *p, int *argc, char *argv[])
{
    (void)argc;
    (void)argv;

    /* Recover core_results* from the embedded core_portable member */
    s_results_ptr = (void *)((char *)p - offsetof(core_results, port));

    /* Initialize SEGGER RTT control block early so the J-Link host can
     * locate it as soon as the firmware boots.  NO_BLOCK_TRIM means writes
     * that overflow the 32 KB up-buffer are dropped instead of stalling. */
    SEGGER_RTT_ConfigUpBuffer(0, "CoreMark", NULL, 0,
                              SEGGER_RTT_MODE_NO_BLOCK_TRIM);

    /* Full SoC init: caches, SWO debug output (starts in HP mode) */
    nsx_system_init(&nsx_system_development);

#ifndef COREMARK_HP_MODE
    /* Switch to LP 96 MHz NOW, before the timed CoreMark run.
     * This ensures the score matches the power measurement conditions. */
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Configure power-monitor GPIOs for Joulescope phase detection */
    ns_init_power_monitor_state();

    /* Start the microsecond timer */
    ns_timer_init(&s_timer_cfg);

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

#ifndef COREMARK_SCORE_ONLY
#ifdef COREMARK_HP_MODE
    ee_printf("--- Staying at HP 250 MHz for active power measurement. ---\n");
#else
    ee_printf("--- Switching to LP 96 MHz for active power measurement. ---\n");
#endif

    /* Brief delay to let SWO flush */
    ns_delay_us(200000);

    /* Disable ITM/SWO — no more prints after this */
    ns_itm_printf_disable();

    /* Aggressive power-down: everything off, LP mode, NO SpotManager */
    static const ns_power_config_t coremark_power = {
        .api               = &ns_power_V1_0_0,
        .perf_mode         = NS_PERF_LOW,
        .need_audadc       = false,
        .need_ssram        = false,
        .need_crypto       = false,
        .need_ble          = false,
        .need_usb          = false,
        .need_iom          = false,
        .need_uart         = false,
        .small_tcm         = true,
        .need_tempco       = false,
        .need_itm          = false,
        .need_xtal         = false,
        .spotmgr_collapse  = false,
    };
    ns_power_config(&coremark_power);

    /* Nuclear peripheral kill */
    am_hal_pwrctrl_control(AM_HAL_PWRCTRL_CONTROL_DIS_PERIPHS_ALL, 0);
    am_hal_pwrctrl_control(AM_HAL_PWRCTRL_CONTROL_XTAL_PWDN_DEEPSLEEP, 0);

    /* Stop ALL timers */
    for (uint32_t t = 0; t < 16; t++) {
        am_hal_timer_stop(t);
    }

    /* Reduce memory: 32K ITCM + 128K DTCM, single NVM bank, SSRAM off */
    am_hal_pwrctrl_mcu_memory_config_t McuMemCfg = {
        .eROMMode              = AM_HAL_PWRCTRL_ROM_AUTO,
        .eDTCMCfg              = AM_HAL_PWRCTRL_ITCM32K_DTCM128K,
        .eRetainDTCM           = AM_HAL_PWRCTRL_MEMRETCFG_TCMPWDSLP_RETAIN,
        .eNVMCfg               = AM_HAL_PWRCTRL_NVM0_ONLY,
        .bKeepNVMOnInDeepSleep = false,
    };
    am_hal_pwrctrl_mcu_memory_config(&McuMemCfg);

    am_hal_pwrctrl_sram_memcfg_t SRAMMemCfg = {
        .eSRAMCfg        = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithMCU  = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithGFX  = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithDISP = AM_HAL_PWRCTRL_SRAM_NONE,
        .eSRAMRetain     = AM_HAL_PWRCTRL_SRAM_NONE,
    };
    am_hal_pwrctrl_sram_config(&SRAMMemCfg);

    /* MRAM low-power read mode */
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.MRAM0PWRCTRL = 1;
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.MRAM0LPREN   = 1;
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.CRYPTOCLKGATEN = 1;

    /* Clear debug control */
    MCUCTRL->DBGCTRL = 0;

    /* Force target clock LAST */
#ifdef COREMARK_HP_MODE
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_HIGH_PERFORMANCE);
#else
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Tristate all unused GPIOs */
    for (uint32_t pin = 0; pin < AM_HAL_GPIO_MAX_PADS; pin++) {
        if (pin == NS_POWER_MONITOR_GPIO_0 || pin == NS_POWER_MONITOR_GPIO_1)
            continue;
        am_hal_gpio_pinconfig(pin, am_hal_gpio_pincfg_disabled);
    }

    /* Jump to ITCM-resident loop: shuts off NVM + caches + remaining
     * peripheral enables, then runs CoreMark iterate() forever from
     * zero-wait-state SRAM.  No return. */
    itcm_power_loop(s_results_ptr);
#endif /* !COREMARK_SCORE_ONLY */

    /* Spin so the score stays visible on SWO */
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
        /* J-Link reads the RTT control block + ring buffer over SWD, which
         * bypasses the CPU D-cache.  Clean the cache so the J-Link host can
         * see the latest WrOff and bytes. */
        SCB_CleanDCache();
    }
    return n;
}
