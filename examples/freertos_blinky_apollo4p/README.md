# freertos_blinky_apollo4p

Reference **nsx** application that runs the optional `nsx-freertos` module on
the Apollo4P Blue KXR EVB. It creates a single FreeRTOS task that prints a tick
counter (and the vendored kernel version) once every 500 ms, then starts the
scheduler.

This example is the canonical Cortex-M4F (`ARM_CM4F`) companion to
[../freertos_blinky](../freertos_blinky): it demonstrates the same
`nsx::freertos_config` contract and application-owned hooks, but exercises the
indirect handler-routing path validated on Apollo4P hardware.

## How FreeRTOS is wired in

The `nsx-freertos` module deliberately does **not** ship a `FreeRTOSConfig.h`.
Kernel configuration is application policy, so the app publishes it through the
`nsx::freertos_config` interface target. This example does that in
[CMakeLists.txt](CMakeLists.txt) **before** `nsx_bootstrap_app()` adds the
module:

```cmake
add_library(app_freertos_config INTERFACE)
target_include_directories(app_freertos_config INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/config)
add_library(nsx::freertos_config ALIAS app_freertos_config)
```

The kernel config lives in [config/FreeRTOSConfig.h](config/FreeRTOSConfig.h)
(seeded from the module template). On Cortex-M4F, `nsx-freertos` provides strong
shim `SVC_Handler`, `PendSV_Handler`, and `SysTick_Handler` symbols that route
the weak NSX startup vectors to FreeRTOS' `vPortSVCHandler`,
`xPortPendSVHandler`, and `xPortSysTickHandler` entry points. No handler
remapping macros are needed in the application.

The application also provides the hooks the config enables
(`vApplicationMallocFailedHook`, `vApplicationStackOverflowHook`) in
[src/main.c](src/main.c).

## Build & Run

```bash
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires JLink + Apollo4P Blue KXR EVB
nsx view      --app-dir .      # opens SWO viewer
```

## Expected Output

```text
freertos_blinky: starting scheduler
freertos_blinky: tick 0 (kernel V11.1.0)
freertos_blinky: tick 1 (kernel V11.1.0)
freertos_blinky: tick 2 (kernel V11.1.0)
...
```

Messages repeat roughly twice per second. If you see only the
`starting scheduler` line, the scheduler failed to start — check that the
SoC's `NSX_SOC_RTOS_PORT_GENERIC` resolves to `ARM_CM4F` (Apollo4P does) and
that the example's application-owned `FreeRTOSConfig.h` stays aligned with the
current SDK template.
