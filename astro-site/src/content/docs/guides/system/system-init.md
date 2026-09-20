---
title: System initialization
description: The two initialization layers a generated app can call, what each one configures, and how to turn on SWO or UART output.
---

A generated app starts with the smallest thing that works: bring the runtime core up,
enable an output transport, then run. There is a second, larger entry point for when you
want clocks, caches and the BSP configured as well.

:::note[These declarations come from a vendored module]
The headers below ship in the `nsx-core` module inside the SDK that your app vendors, not
in the NSX package. In your app they are under
`modules/nsx-ambiq-sdk/modules/nsx-core/includes-api/`. The copy in your app is the
authoritative one, because the SDK revision NSX pins differs by SoC family.
:::

## The minimum: `nsx_core_init`

This is what `nsx create-app` generates:

```c
#include "nsx_core.h"

int main(void)
{
    nsx_core_config_t cfg = {
        .api = &nsx_core_V1_0_0,
    };
    (void)nsx_core_init(&cfg);

    nsx_itm_printf_enable();

    while (1) {
        nsx_printf("nsx hello from generated app\r\n");
        nsx_delay_us(1000000);
    }
}
```

`nsx_core_config_t` carries one field, a pointer to the core API version the app was built
against:

```c
typedef struct {
    const nsx_core_api_t *api; ///< Core API version
} nsx_core_config_t;

extern const nsx_core_api_t nsx_core_V1_0_0;
extern bool nsx_core_initialized(void);
extern uint32_t nsx_core_init(nsx_core_config_t *c);
```

Passing the version explicitly is what lets the core reject an app built against an API it
no longer implements, rather than failing somewhere less obvious. `nsx_core_initialized()`
answers whether the call has happened, which is useful in library code that cannot assume
it ran.

### Output transports

Nothing prints until you enable a transport. The core header declares three pairs:

```c
void nsx_itm_printf_enable(void);
void nsx_itm_printf_disable(void);
void nsx_uart_printf_enable(void);
void nsx_uart_printf_disable(void);
void nsx_debug_printf_enable(void);
void nsx_debug_printf_disable(void);
```

ITM is SWO, which is what [`nsx view`](/neuralspotx/guides/apps/build-flash-view/) reads,
and it needs a J-Link and a connected SWO pin. UART needs the BSP's UART pins. Once one is
enabled, `nsx_printf()` goes to it. `nsx_low_power_printf()` is the variant for code paths
where you care about what printing costs.

The rest of the core surface is small: `nsx_delay_us()`, and
`nsx_interrupt_master_enable()` and `nsx_interrupt_master_disable()`.

:::tip[No SWO output at all?]
The usual cause is the transport, not the firmware. Check that
`nsx_itm_printf_enable()` runs before the first `nsx_printf()`, and see the SWO section of
[Troubleshooting](/neuralspotx/guides/apps/troubleshooting/) for the attach-without-reset
behavior that hides early output on some SoCs.
:::

## The full path: `nsx_system_init`

`nsx_system.h` is a one-call convenience layer over the same hardware. Use it when you
want the performance mode, the caches, the BSP and the debug transport configured
together:

```c
uint32_t nsx_system_init(const nsx_system_config_t *cfg);
```

```c
typedef struct {
    nsx_perf_mode_e    perf_mode;      ///< CPU performance mode
    bool               enable_cache;   ///< Enable I/D cache on staged R5 targets
    bool               enable_sram;    ///< Reserved - keep shared SRAM powered (not yet wired)
    nsx_debug_config_t debug;          ///< Debug output config
    bool               skip_bsp_init;  ///< Skip am_bsp_low_power_init() (use minimal HW init)
    bool               spot_mgr_profile;///< Enable SpotManager profile (Apollo5 family only)
} nsx_system_config_t;
```

`enable_sram` is marked in the header as reserved and not wired, so setting it does
nothing today. `spot_mgr_profile` is documented in the header as applying to the Apollo5
family only.

### Performance and debug modes

```c
typedef enum {
    NSX_PERF_LOW    = 0,   ///< Low-power mode
    NSX_PERF_MEDIUM = 1,   ///< Medium performance (HP1 on AP330P/510L)
    NSX_PERF_HIGH   = 2,   ///< High performance  (HP2 on AP330P/510L)
} nsx_perf_mode_e;

typedef enum {
    NSX_DEBUG_NONE = 0,    ///< No debug output
    NSX_DEBUG_ITM  = 1,    ///< SWO/ITM (requires JLink + SWO pin)
    NSX_DEBUG_UART = 2,    ///< UART (requires BSP UART pins)
} nsx_debug_transport_e;
```

What each performance mode maps to in silicon is an SoC property, and the header names the
mapping only for the parts where it differs. Check the datasheet for the part you are
targeting rather than assuming the enum is portable across families.

### The pieces underneath

`nsx_system_init()` composes four calls that are also public, so you can take only the
parts you want:

```c
uint32_t nsx_hw_init(void);          // full staged hardware init, through the BSP
uint32_t nsx_minimal_hw_init(void);  // minimal init, no BSP
uint32_t nsx_set_perf_mode(nsx_perf_mode_e mode);
uint32_t nsx_debug_init(const nsx_debug_config_t *cfg);
```

`skip_bsp_init` in the config is what selects `nsx_minimal_hw_init()` over
`nsx_hw_init()`. Reach for it when the BSP's low-power setup conflicts with what you are
measuring, which is the usual case in a power benchmark.

## Which one to use

Start with `nsx_core_init()`. It is what the generated app does and it is enough to print,
delay and run your own code.

Move to `nsx_system_init()` when you need the caches on, a specific performance mode, or
the BSP configured. Enabling caches is also where
[memory placement](/neuralspotx/guides/system/memory-placement/) starts to matter, because
what a cache does for you depends on which region your hot code and data ended up in.
