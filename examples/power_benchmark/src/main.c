/**
 * @file main.c
 * @brief Power Benchmark — Deep Sleep, While(1), and CoreMark
 *
 * Three benchmark modes selected at compile time via BENCHMARK_MODE:
 *
 *   coremark     — EEMBC CoreMark from ITCM with NVM off  (active compute)
 *   coremark_nvm — EEMBC CoreMark from NVM with all memory on (datasheet config)
 *   coremark_minmem — EEMBC CoreMark from NVM, SDK5-equivalent minimal memory
 *   coremark_sdk5 — EEMBC CoreMark with SDK5-verbatim init + power-down (UART)
 *   while1       — Tight NOP loop from ITCM with NVM off  (active baseline)
 *   deepsleep    — WFI deep sleep with minimal peripherals (sleep baseline)
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
#if !defined(BENCHMARK_NVM_ALL_ON) && !defined(BENCHMARK_NVM_MINMEM)
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
#endif /* !BENCHMARK_NVM_ALL_ON && !BENCHMARK_NVM_MINMEM */

/* ===================================================================
 * Common power-down sequence (ITCM modes — NVM off)
 *
 * Uses nsx-power helpers in the documented order.  No raw register
 * writes — each step is a single, auditable function call.
 * =================================================================== */
#if !defined(BENCHMARK_NVM_ALL_ON) && !defined(BENCHMARK_NVM_MINMEM)
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
#endif /* !BENCHMARK_NVM_ALL_ON && !BENCHMARK_NVM_MINMEM */

/* ===================================================================
 * NVM all-memory-on measurement
 *
 * CoreMark runs from NVM (MRAM) with both NVM banks + SSRAM powered.
 * Caches stay enabled.  Only peripherals, debug, and unused GPIOs are
 * disabled — this matches the "typical Coremark power with all memory"
 * configuration requested for datasheet numbers.
 * =================================================================== */
#ifdef BENCHMARK_NVM_ALL_ON
static void __attribute__((noreturn))
enter_nvm_power_measurement(void *benchmark_arg)
{
    ns_printf("Entering NVM all-memory-on power measurement...\n");
    ns_delay_us(200000); /* let SWO flush */

    /* Step 1: Disable SWO/ITM */
    ns_itm_printf_disable();
    ns_power_disable_debug();

    /* Step 2: Shut down all non-core peripherals + timers */
    ns_power_shutdown_peripherals();

    /* Step 3: Do NOT minimize memory — keep all NVM + SSRAM powered.
     * MRAM low-power read mode is fine; just don't shrink TCM or
     * disable NVM banks. */

    /* Step 4: Tristate unused GPIOs */
    const uint32_t keep[] = {
        NS_POWER_MONITOR_GPIO_0,
        NS_POWER_MONITOR_GPIO_1,
    };
    ns_power_tristate_gpios(keep, 2);

    /* Step 5: Select target clock mode */
#ifdef BENCHMARK_HP_MODE
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_HIGH_PERFORMANCE);
#else
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Signal ACTIVE phase to Joulescope */
    am_hal_gpio_output_set(NS_POWER_MONITOR_GPIO_0);
    am_hal_gpio_output_clear(NS_POWER_MONITOR_GPIO_1);

    /* CoreMark iterate() runs from NVM via I-cache.
     * NVM stays on, caches stay on — this is the "all memory on" config. */
    while (1) {
        iterate(benchmark_arg);
    }
}
#endif /* BENCHMARK_NVM_ALL_ON */

/* ===================================================================
 * NVM minimal-memory measurement (SDK5 COREMARK_DEFAULT equivalent)
 *
 * CoreMark runs from NVM (MRAM) via I-cache with power-optimized
 * memory configuration: minimal TCM, NVM0 only, no SSRAM, MRAM LP
 * read mode, ELP retention, RTC oscillator disabled.
 *
 * This matches the AmbiqSuite SDK5 coremark default configuration
 * for apples-to-apples power comparison.
 * =================================================================== */
#ifdef BENCHMARK_NVM_MINMEM

static void __attribute__((noreturn))
enter_minmem_power_measurement(void *benchmark_arg)
{
    ns_printf("Entering NVM min-memory power measurement...\n");

    /* I-cache warm-up */
    for (int i = 0; i < 3; i++) {
        iterate(benchmark_arg);
    }

    ns_delay_us(200000); /* let SWO flush */

    /* Step 1: Disable SWO/ITM */
    ns_itm_printf_disable();
    ns_power_disable_debug();

    /* Step 2: Shut down all non-core peripherals + timers */
    ns_power_shutdown_peripherals();

    /* Step 3: Minimize memory — matches SDK5 apollo5_cache_memory_config()
     * with ALL_RETAIN=0: ITCM32K+DTCM128K, NVM0_ONLY, SRAM_NONE,
     * MRAM LP read mode, crypto clock gate. */
    ns_power_minimize_memory();

    /* Step 4: ELP retention (SDK5 uses ELP_RET for COREMARK_DEFAULT) */
    am_hal_pwrctrl_pwrmodctl_cpdlp_t cpdlp = {
        .eRlpConfig = AM_HAL_PWRCTRL_RLP_ON,
        .eElpConfig = AM_HAL_PWRCTRL_ELP_RET,
        .eClpConfig = AM_HAL_PWRCTRL_CLP_ON,
    };
    am_hal_pwrctrl_pwrmodctl_cpdlp_config(cpdlp);

    /* Step 5: Disable RTC oscillator (SDK5 switches to LFRC then disables) */
    am_hal_rtc_osc_select(AM_HAL_RTC_OSC_LFRC);
    am_hal_rtc_osc_disable();

    /* Step 6: Explicit clock gate */
    CLKGEN->CLKCTRL = 0x0;

    /* Step 7: Tristate ALL GPIOs */
    ns_power_tristate_gpios(NULL, 0);

    /* Step 8: Select LP mode */
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);

    /* CoreMark iterate() runs from NVM via I-cache. */
    while (1) {
        iterate(benchmark_arg);
    }
}
#endif /* BENCHMARK_NVM_MINMEM */

/* ===================================================================
 * SDK5-mimic measurement (verbatim AmbiqSuite coremark sequence)
 *
 * Bypasses all NSX framework power helpers and follows the exact
 * SDK5 portable_init() power-down sequence step-by-step:
 *   - Individual am_hal_pwrctrl_periph_disable (not DIS_PERIPHS_ALL)
 *   - No DCU unlock, no SWO/ITM, no GPIO tristate, no CLKCTRL=0
 *   - Memory config via direct HAL struct (apollo5_cache_memory_config)
 *
 * If this reaches the same ~1.926 mA as the SDK5 prebuilt binary,
 * the remaining gap in coremark_minmem is due to NSX framework overhead.
 * =================================================================== */
#ifdef BENCHMARK_SDK5_MIMIC

/* ---------------------------------------------------------------
 * Register dump — captures all power-critical registers via UART.
 * Format: "REG_NAME = 0xHHHHHHHH\n" — easy to diff against SDK5.
 * UART is enabled/disabled around the dump so it doesn't affect
 * the measurement.
 * --------------------------------------------------------------- */
static void
dump_power_registers(void)
{
    am_bsp_uart_printf_enable();
    am_util_stdio_printf("\n=== REGISTER DUMP (pre-measurement) ===\n");

    /* --- PWRCTRL registers --- */
    am_util_stdio_printf("PWRCTRL.MCUPERFREQ       = 0x%08X\n", PWRCTRL->MCUPERFREQ);
    am_util_stdio_printf("PWRCTRL.DEVPWREN         = 0x%08X\n", PWRCTRL->DEVPWREN);
    am_util_stdio_printf("PWRCTRL.DEVPWRSTATUS     = 0x%08X\n", PWRCTRL->DEVPWRSTATUS);
    am_util_stdio_printf("PWRCTRL.AUDSSPWREN       = 0x%08X\n", PWRCTRL->AUDSSPWREN);
    am_util_stdio_printf("PWRCTRL.AUDSSPWRSTATUS   = 0x%08X\n", PWRCTRL->AUDSSPWRSTATUS);
    am_util_stdio_printf("PWRCTRL.MEMPWREN         = 0x%08X\n", PWRCTRL->MEMPWREN);
    am_util_stdio_printf("PWRCTRL.MEMPWRSTATUS     = 0x%08X\n", PWRCTRL->MEMPWRSTATUS);
    am_util_stdio_printf("PWRCTRL.MEMRETCFG        = 0x%08X\n", PWRCTRL->MEMRETCFG);
    am_util_stdio_printf("PWRCTRL.SYSPWRSTATUS     = 0x%08X\n", PWRCTRL->SYSPWRSTATUS);
    am_util_stdio_printf("PWRCTRL.SSRAMPWREN       = 0x%08X\n", PWRCTRL->SSRAMPWREN);
    am_util_stdio_printf("PWRCTRL.SSRAMPWRST       = 0x%08X\n", PWRCTRL->SSRAMPWRST);
    am_util_stdio_printf("PWRCTRL.SSRAMRETCFG      = 0x%08X\n", PWRCTRL->SSRAMRETCFG);
    am_util_stdio_printf("PWRCTRL.DEVPWREVENTEN    = 0x%08X\n", PWRCTRL->DEVPWREVENTEN);
    am_util_stdio_printf("PWRCTRL.MEMPWREVENTEN    = 0x%08X\n", PWRCTRL->MEMPWREVENTEN);
    am_util_stdio_printf("PWRCTRL.MMSOVERRIDE      = 0x%08X\n", PWRCTRL->MMSOVERRIDE);
    am_util_stdio_printf("PWRCTRL.CPUPWRCTRL       = 0x%08X\n", PWRCTRL->CPUPWRCTRL);
    am_util_stdio_printf("PWRCTRL.PWRCTRLMODESTATUS = 0x%08X\n", PWRCTRL->PWRCTRLMODESTATUS);
    am_util_stdio_printf("PWRCTRL.CPUPWRSTATUS     = 0x%08X\n", PWRCTRL->CPUPWRSTATUS);
    am_util_stdio_printf("PWRCTRL.VRCTRL           = 0x%08X\n", PWRCTRL->VRCTRL);
    am_util_stdio_printf("PWRCTRL.LEGACYVRLPOVR    = 0x%08X\n", PWRCTRL->LEGACYVRLPOVR);
    am_util_stdio_printf("PWRCTRL.VRSTATUS         = 0x%08X\n", PWRCTRL->VRSTATUS);
    am_util_stdio_printf("PWRCTRL.SRAMCTRL         = 0x%08X\n", PWRCTRL->SRAMCTRL);
    am_util_stdio_printf("PWRCTRL.TONCNTRCTRL      = 0x%08X\n", PWRCTRL->TONCNTRCTRL);
    am_util_stdio_printf("PWRCTRL.LPOVRTHRESHVDDS  = 0x%08X\n", PWRCTRL->LPOVRTHRESHVDDS);
    am_util_stdio_printf("PWRCTRL.LPOVRHYSTCNT     = 0x%08X\n", PWRCTRL->LPOVRHYSTCNT);
    am_util_stdio_printf("PWRCTRL.LPOVRTHRESHVDDF  = 0x%08X\n", PWRCTRL->LPOVRTHRESHVDDF);
    am_util_stdio_printf("PWRCTRL.LPOVRTHRESHVDDC  = 0x%08X\n", PWRCTRL->LPOVRTHRESHVDDC);
    am_util_stdio_printf("PWRCTRL.LPOVRTHRESHVDDCLV = 0x%08X\n", PWRCTRL->LPOVRTHRESHVDDCLV);
    am_util_stdio_printf("PWRCTRL.MRAMEXTCTRL      = 0x%08X\n", PWRCTRL->MRAMEXTCTRL);
    am_util_stdio_printf("PWRCTRL.EMONCTRL         = 0x%08X\n", PWRCTRL->EMONCTRL);
    am_util_stdio_printf("PWRCTRL.GFXPERFREQ       = 0x%08X\n", PWRCTRL->GFXPERFREQ);
    am_util_stdio_printf("PWRCTRL.EPURETCFG        = 0x%08X\n", PWRCTRL->EPURETCFG);

    /* --- MCUCTRL registers --- */
    am_util_stdio_printf("MCUCTRL.SIMOBUCK0        = 0x%08X\n", MCUCTRL->SIMOBUCK0);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK1        = 0x%08X\n", MCUCTRL->SIMOBUCK1);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK2        = 0x%08X\n", MCUCTRL->SIMOBUCK2);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK3        = 0x%08X\n", MCUCTRL->SIMOBUCK3);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK4        = 0x%08X\n", MCUCTRL->SIMOBUCK4);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK5        = 0x%08X\n", MCUCTRL->SIMOBUCK5);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK6        = 0x%08X\n", MCUCTRL->SIMOBUCK6);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK7        = 0x%08X\n", MCUCTRL->SIMOBUCK7);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK8        = 0x%08X\n", MCUCTRL->SIMOBUCK8);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK9        = 0x%08X\n", MCUCTRL->SIMOBUCK9);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK10       = 0x%08X\n", MCUCTRL->SIMOBUCK10);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK11       = 0x%08X\n", MCUCTRL->SIMOBUCK11);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK12       = 0x%08X\n", MCUCTRL->SIMOBUCK12);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK13       = 0x%08X\n", MCUCTRL->SIMOBUCK13);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK14       = 0x%08X\n", MCUCTRL->SIMOBUCK14);
    am_util_stdio_printf("MCUCTRL.SIMOBUCK15       = 0x%08X\n", MCUCTRL->SIMOBUCK15);
    am_util_stdio_printf("MCUCTRL.LDOREG1          = 0x%08X\n", MCUCTRL->LDOREG1);
    am_util_stdio_printf("MCUCTRL.LDOREG2          = 0x%08X\n", MCUCTRL->LDOREG2);
    am_util_stdio_printf("MCUCTRL.VRCTRL           = 0x%08X\n", MCUCTRL->VRCTRL);
    am_util_stdio_printf("MCUCTRL.VREFGEN2         = 0x%08X\n", MCUCTRL->VREFGEN2);
    am_util_stdio_printf("MCUCTRL.VREFGEN4         = 0x%08X\n", MCUCTRL->VREFGEN4);
    am_util_stdio_printf("MCUCTRL.VREFBUF          = 0x%08X\n", MCUCTRL->VREFBUF);
    am_util_stdio_printf("MCUCTRL.ACRG             = 0x%08X\n", MCUCTRL->ACRG);
    am_util_stdio_printf("MCUCTRL.BGTLPCTRL        = 0x%08X\n", MCUCTRL->BGTLPCTRL);
    am_util_stdio_printf("MCUCTRL.MRAMCRYPTOPWRCTRL = 0x%08X\n", MCUCTRL->MRAMCRYPTOPWRCTRL);
    am_util_stdio_printf("MCUCTRL.BODISABLE        = 0x%08X\n", MCUCTRL->BODISABLE);
    am_util_stdio_printf("MCUCTRL.BODCTRL          = 0x%08X\n", MCUCTRL->BODCTRL);
    am_util_stdio_printf("MCUCTRL.DBGCTRL          = 0x%08X\n", MCUCTRL->DBGCTRL);
    am_util_stdio_printf("MCUCTRL.PWRSW0           = 0x%08X\n", MCUCTRL->PWRSW0);
    am_util_stdio_printf("MCUCTRL.PWRSW1           = 0x%08X\n", MCUCTRL->PWRSW1);
    am_util_stdio_printf("MCUCTRL.PWRSW2           = 0x%08X\n", MCUCTRL->PWRSW2);
    am_util_stdio_printf("MCUCTRL.ADCPWRCTRL       = 0x%08X\n", MCUCTRL->ADCPWRCTRL);
    am_util_stdio_printf("MCUCTRL.AUDADCPWRCTRL    = 0x%08X\n", MCUCTRL->AUDADCPWRCTRL);
    am_util_stdio_printf("MCUCTRL.PDMCTRL          = 0x%08X\n", MCUCTRL->PDMCTRL);
    am_util_stdio_printf("MCUCTRL.MMSMISCCTRL      = 0x%08X\n", MCUCTRL->MMSMISCCTRL);
    am_util_stdio_printf("MCUCTRL.CPUCFG           = 0x%08X\n", MCUCTRL->CPUCFG);

    /* --- CLKGEN registers --- */
    am_util_stdio_printf("CLKGEN.CLKCTRL           = 0x%08X\n", CLKGEN->CLKCTRL);
    am_util_stdio_printf("CLKGEN.OCTRL             = 0x%08X\n", CLKGEN->OCTRL);
    am_util_stdio_printf("CLKGEN.CLKOUT            = 0x%08X\n", CLKGEN->CLKOUT);
    am_util_stdio_printf("CLKGEN.CLOCKENSTAT       = 0x%08X\n", CLKGEN->CLOCKENSTAT);
    am_util_stdio_printf("CLKGEN.CLOCKEN2STAT      = 0x%08X\n", CLKGEN->CLOCKEN2STAT);
    am_util_stdio_printf("CLKGEN.CLOCKEN3STAT      = 0x%08X\n", CLKGEN->CLOCKEN3STAT);
    am_util_stdio_printf("CLKGEN.LFRCCTRL          = 0x%08X\n", CLKGEN->LFRCCTRL);
    am_util_stdio_printf("CLKGEN.MISC              = 0x%08X\n", CLKGEN->MISC);
    am_util_stdio_printf("CLKGEN.HFADJ             = 0x%08X\n", CLKGEN->HFADJ);
    am_util_stdio_printf("CLKGEN.HF2ADJ0           = 0x%08X\n", CLKGEN->HF2ADJ0);
    am_util_stdio_printf("CLKGEN.HF2ADJ1           = 0x%08X\n", CLKGEN->HF2ADJ1);
    am_util_stdio_printf("CLKGEN.HF2ADJ2           = 0x%08X\n", CLKGEN->HF2ADJ2);
    am_util_stdio_printf("CLKGEN.DISPCLKCTRL       = 0x%08X\n", CLKGEN->DISPCLKCTRL);

    am_util_stdio_printf("=== END REGISTER DUMP ===\n\n");
    am_bsp_uart_printf_disable();
}

static void __attribute__((noreturn))
enter_sdk5_power_measurement(void *benchmark_arg)
{
    /* --- CPDLP: ELP retention (SDK5: ELP_ON=0 → ELP_RET) --- */
    am_hal_pwrctrl_pwrmodctl_cpdlp_t cpdlp = {
        .eRlpConfig = AM_HAL_PWRCTRL_RLP_ON,
        .eElpConfig = AM_HAL_PWRCTRL_ELP_RET,
        .eClpConfig = AM_HAL_PWRCTRL_CLP_ON,
    };
    am_hal_pwrctrl_pwrmodctl_cpdlp_config(cpdlp);

    /* --- I-cache warmup (equivalent to SDK5 icache_prefill) --- */
    for (int i = 0; i < 3; i++) {
        iterate(benchmark_arg);
    }

    /* --- RTC oscillator: switch to LFRC, then disable --- */
    am_hal_rtc_osc_select(AM_HAL_RTC_OSC_LFRC);
    am_hal_rtc_osc_disable();

    /* --- VCOMP power down --- */
    VCOMP->PWDKEY = VCOMP_PWDKEY_PWDKEY_Key;

    /* --- Debug: zero DBGCTRL, then disable peripheral --- */
    MCUCTRL->DBGCTRL = 0;

    /* --- Individual peripheral disable (exactly SDK5 order) --- */
    am_hal_pwrctrl_periph_disable(AM_HAL_PWRCTRL_PERIPH_DEBUG);
    am_hal_pwrctrl_periph_disable(AM_HAL_PWRCTRL_PERIPH_CRYPTO);
    am_hal_pwrctrl_periph_disable(AM_HAL_PWRCTRL_PERIPH_OTP);

    /* --- Memory config: SDK5 apollo5_cache_memory_config() --- */
    am_hal_pwrctrl_mcu_memory_config_t McuMemCfg = {
        .eROMMode              = AM_HAL_PWRCTRL_ROM_AUTO,
        .eDTCMCfg              = AM_HAL_PWRCTRL_ITCM32K_DTCM128K,
        .eRetainDTCM           = AM_HAL_PWRCTRL_MEMRETCFG_TCMPWDSLP_RETAIN,
        .eNVMCfg               = AM_HAL_PWRCTRL_NVM0_ONLY,
        .bKeepNVMOnInDeepSleep = false,
    };
    am_hal_pwrctrl_mcu_memory_config(&McuMemCfg);

    MCUCTRL->MRAMCRYPTOPWRCTRL_b.MRAM0LPREN   = 1;
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.MRAM0SLPEN   = 0;
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.MRAM0PWRCTRL = 1;

    am_hal_pwrctrl_sram_memcfg_t SRAMMemCfg = {
        .eSRAMCfg        = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithMCU  = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithGFX  = AM_HAL_PWRCTRL_SRAM_NONE,
        .eActiveWithDISP = AM_HAL_PWRCTRL_SRAM_NONE,
        .eSRAMRetain     = AM_HAL_PWRCTRL_SRAM_NONE,
    };
    am_hal_pwrctrl_sram_config(&SRAMMemCfg);

    /* --- FPU enable + lazy stacking (explicit, like SDK5) --- */
    am_hal_sysctrl_fpu_enable();
    am_hal_sysctrl_fpu_stacking_enable(true);

    /* --- MCU mode: Low Power 96 MHz --- */
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);

    /* --- Crypto clock gate --- */
    MCUCTRL->MRAMCRYPTOPWRCTRL_b.CRYPTOCLKGATEN = 1;

    /* --- Register dump: capture final state before measurement --- */
    dump_power_registers();

    /* --- Run forever in SDK5-identical state --- */
    while (1) {
        iterate(benchmark_arg);
    }
}
#endif /* BENCHMARK_SDK5_MIMIC */

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
#ifdef BENCHMARK_SDK5_MIMIC
    /* ---------------------------------------------------------------
     * SDK5-identical init — bypass NSX system init entirely.
     * Only ns_core_init is needed for the timer in core_portme.c.
     * --------------------------------------------------------------- */
    ns_core_config_t core_cfg = { .api = &ns_core_V1_0_0 };
    ns_core_init(&core_cfg);

    /* BSP init (identical to SDK5 portable_init first call):
     * 2 s delay, am_hal_pwrctrl_low_power_init, caches, SIMOBUCK_INIT,
     * temp 25 °C, clkmgr board info, HFRC/HFRC2 config. */
    am_bsp_low_power_init();

    /* UART output (SDK5 uses UART, not SWO) */
    am_bsp_uart_printf_enable();
    am_util_stdio_printf("\n=== Power Benchmark: SDK5-mimic LP 96 MHz ===\n");
    am_util_stdio_printf("Mode: CoreMark (NVM, SDK5-identical sequence)\n");
    am_bsp_uart_printf_disable();

    /* Run timed CoreMark — gets s_coremark_results via portable_fini */
    coremark_main();

    /* Stop the timer started by core_portme.c (SDK5 stops SysTick) */
    am_hal_timer_stop(0);

    /* Enter SDK5-identical power-down + measurement loop (no return) */
    enter_sdk5_power_measurement(s_coremark_results);
#else
    /* For minmem mode, use a custom config that never enters HP mode.
     * The HP→LP SIMOBUCK/LDO transition can leave residual trim state
     * that differs from a direct LP boot (as SDK5 does). */
#ifdef BENCHMARK_NVM_MINMEM
    static const nsx_system_config_t minmem_cfg = {
        .perf_mode        = NSX_PERF_LOW,
        .enable_cache     = true,
        .enable_sram      = false,
        .debug            = { .transport = NSX_DEBUG_ITM },
        .skip_bsp_init    = false,
        .spot_mgr_profile = false,
    };
    nsx_system_init(&minmem_cfg);
#else
    /* Full system init: caches, clocks, SWO debug output */
    nsx_system_init(&nsx_system_development);
#endif

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

#ifdef BENCHMARK_NVM_ALL_ON
    ns_printf("Mode: CoreMark (NVM execution, all memory on)\n");
#elif defined(BENCHMARK_NVM_MINMEM)
    ns_printf("Mode: CoreMark (NVM execution, minimal memory — SDK5 match)\n");
#else
    ns_printf("Mode: CoreMark (ITCM execution, NVM off)\n");
#endif

    /* Switch to target clock BEFORE CoreMark timing so the score
     * matches the power measurement conditions. */
#ifndef BENCHMARK_HP_MODE
    am_hal_pwrctrl_mcu_mode_select(AM_HAL_PWRCTRL_MCU_MODE_LOW_POWER);
#endif

    /* Run the timed CoreMark benchmark — prints score via SWO */
    coremark_main();

    /* Enter power measurement with iterate() as the workload */
#ifdef BENCHMARK_NVM_ALL_ON
    enter_nvm_power_measurement(s_coremark_results);
#elif defined(BENCHMARK_NVM_MINMEM)
    enter_minmem_power_measurement(s_coremark_results);
#else
    enter_power_measurement(s_coremark_results);
#endif

#else /* BENCHMARK_WHILE1 (default) */
    ns_printf("Mode: While(1)\n");
    enter_power_measurement(NULL);
#endif
#endif /* BENCHMARK_SDK5_MIMIC */

    /* Never reached */
    while (1) { __WFI(); }
}
