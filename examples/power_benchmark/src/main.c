/**
 * @file main.c
 * @brief Power Benchmark — Deep Sleep, While(1), and CoreMark
 *
 * Three benchmark modes selected at compile time via BENCHMARK_MODE:
 *
 *   coremark   — EEMBC CoreMark from ITCM with NVM off  (active compute)
 *   while1     — Tight NOP loop from ITCM with NVM off  (active baseline)
 *   deepsleep  — WFI deep sleep with minimal peripherals (sleep baseline)
 *
 * All modes use GPIO instrumentation for Joulescope phase detection.
 * Build for each mode, flash, and capture with:
 *   python tools/joulescope_capture.py --duration 60
 *
 * SPDX-License-Identifier: Apache-2.0
 */

#include "nsx_system.h"
#include "nsx_power.h"
#include "ns_timer.h"
#include "ns_ambiqsuite_harness.h"
#include "ns_energy_monitor.h"

#ifdef BENCHMARK_COREMARK
#include "coremark.h"
#include <stddef.h>
#endif

/* ===================================================================
 * ITCM-resident measurement trampoline
 *
 * After the MCU is fully powered down, this function:
 *   1. Powers off NVM (MRAM) — only works from ITCM
 *   2. Disables caches (ITCM is zero-wait-state)
 *   3. Signals ACTIVE to Joulescope via GPIO
 *   4. Runs the benchmark workload forever
 *
 * Everything called from here MUST be in ITCM or DTCM.
 * =================================================================== */
__attribute__((section(".itcm_text"), noinline, noreturn))
static void
itcm_measurement_loop(void *arg)
{
    /* --- Step 6: Power off NVM --- */
    ns_power_disable_nvm();

#ifndef BENCHMARK_COREMARK
    /* --- Step 7: Disable caches (while1 only) ---
     * CoreMark must KEEP the I-cache enabled because GCC emits calls
     * to libc functions (memset, memcmp) that live in MRAM.  After
     * NVM is off, those calls are served entirely from I-cache.
     * The while(1) NOP loop never touches MRAM, so it is safe to
     * disable everything for the lowest baseline current. */
    ns_power_disable_caches();
#endif

    /* Signal ACTIVE phase to Joulescope */
    am_hal_gpio_output_set(NS_POWER_MONITOR_GPIO_0);
    am_hal_gpio_output_clear(NS_POWER_MONITOR_GPIO_1);

    /* Drain the NVM read pipeline.  After ns_power_disable_nvm(),
     * the controller waits for an MRAM bus transaction to finalize.
     * Without this, compilers that inline all library calls (armclang
     * -Ofast) never touch MRAM and NVM stays powered (~1.4 mA extra). */
    NS_POWER_DRAIN_NVM();

#ifdef BENCHMARK_COREMARK
    /* CoreMark iterate() — calls core_bench_list + crcu16, all in ITCM */
    while (1) {
        iterate(arg);
    }
#else
    /* While(1) NOP — absolute minimum active current */
    (void)arg;
    while (1) {
        __NOP();
    }
#endif
}

/* ===================================================================
 * Common power-down sequence
 *
 * Uses nsx-power helpers in the documented order.  No raw register
 * writes — each step is a single, auditable function call.
 * =================================================================== */
static void
enter_power_measurement(void *benchmark_arg)
{
    ns_printf("Entering power measurement...\n");
    ns_delay_us(200000); /* let SWO flush */

    /* Step 1: Disable SWO/ITM — no more prints after this */
    ns_itm_printf_disable();
    ns_power_disable_debug();

    /* Step 2: Shut down all non-core peripherals + timers */
    ns_power_shutdown_peripherals();

    /* Step 3: Minimize memory — 32K ITCM + 128K DTCM, no SSRAM */
    ns_power_minimize_memory();

    /* Step 4: Tristate all GPIOs except power-monitor pins */
    const uint32_t keep[] = {
        NS_POWER_MONITOR_GPIO_0,
        NS_POWER_MONITOR_GPIO_1,
    };
    ns_power_tristate_gpios(keep, 2);

    /* Step 5: Select target clock mode LAST (after peripherals are off) */
#ifdef BENCHMARK_HP_MODE
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_HIGH_PERFORMANCE);
#else
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Steps 6-7 happen inside the ITCM trampoline (NVM off, caches off).
     * No return — this is the last MRAM-resident code that executes. */
    itcm_measurement_loop(benchmark_arg);
}

/* ===================================================================
 * Deep sleep mode — no ITCM trampoline needed
 * =================================================================== */
#ifdef BENCHMARK_DEEPSLEEP
static void __attribute__((noreturn))
enter_deepsleep_measurement(void)
{
    ns_printf("Entering deep sleep measurement...\n");
    ns_delay_us(200000);

    ns_itm_printf_disable();
    ns_power_disable_debug();
    ns_power_shutdown_peripherals();

    /* For deep sleep we keep NVM on (MCU needs it for wakeup path)
     * but still minimize everything else. */
    ns_power_minimize_memory();

    const uint32_t keep[] = {
        NS_POWER_MONITOR_GPIO_0,
        NS_POWER_MONITOR_GPIO_1,
    };
    ns_power_tristate_gpios(keep, 2);

    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);

    /* Signal SLEEP to Joulescope (both GPIOs low) */
    am_hal_gpio_output_clear(NS_POWER_MONITOR_GPIO_0);
    am_hal_gpio_output_clear(NS_POWER_MONITOR_GPIO_1);

    while (1) {
        am_hal_sysctrl_sleep(AM_HAL_SYSCTRL_SLEEP_DEEP);
    }
}
#endif

/* ===================================================================
 * CoreMark hooks
 * =================================================================== */
#ifdef BENCHMARK_COREMARK

/*
 * CoreMark's main() is renamed to coremark_main() via -Dmain=coremark_main
 * in CMakeLists.txt.  We call it from our main(), then take over for
 * power measurement.
 */
extern int coremark_main(void);

/*
 * Stash the core_results pointer so we can pass it to iterate()
 * in the ITCM measurement loop.  portable_fini() sets this.
 */
void *s_coremark_results = NULL;

#endif /* BENCHMARK_COREMARK */

/* ===================================================================
 * Entry point
 * =================================================================== */
int
main(void)
{
    /* Full system init: caches, clocks, SWO debug output */
    nsx_system_init(&nsx_system_development);

    /* Configure power-monitor GPIOs for Joulescope phase detection */
    ns_init_power_monitor_state();

#ifdef BENCHMARK_HP_MODE
    ns_printf("\n=== Power Benchmark: HP 250 MHz ===\n");
#else
    ns_printf("\n=== Power Benchmark: LP 96 MHz ===\n");
#endif

#ifdef BENCHMARK_DEEPSLEEP
    ns_printf("Mode: Deep Sleep\n");
    enter_deepsleep_measurement();

#elif defined(BENCHMARK_COREMARK)
    ns_printf("Mode: CoreMark\n");

    /* Switch to target clock BEFORE CoreMark timing so the score
     * matches the power measurement conditions. */
#ifndef BENCHMARK_HP_MODE
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Run the timed CoreMark benchmark — prints score via SWO */
    coremark_main();

    /* Enter power measurement with iterate() as the workload */
    enter_power_measurement(s_coremark_results);

#else /* BENCHMARK_WHILE1 (default) */
    ns_printf("Mode: While(1)\n");
    enter_power_measurement(NULL);
#endif

    /* Never reached */
    while (1) { __WFI(); }
}
