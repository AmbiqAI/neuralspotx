# freertos_blinky

Reference **nsx** application that runs the optional `nsx-freertos` module on
the Apollo510 EVB and Apollo4P Blue KXR EVB. It creates a single FreeRTOS task
that prints a tick counter (and the vendored kernel version) once every 500 ms,
then starts the scheduler.

This is the canonical integration example for the FreeRTOS enablement work:
it demonstrates the `nsx::freertos_config` contract, application-owned hooks,
and both FreeRTOS port paths exercised by NSX today: Cortex-M55
(`ARM_CM55_NTZ`) on Apollo510 and Cortex-M4F (`ARM_CM4F`) on Apollo4P.

The manifest is also a **multi-target** proving ground: a single lean
`nsx.yml` declares a `targets:` block for both boards and layers the
optional `nsx-freertos` module via `requires:` on top of each board's derived
`<board>_minimal` profile.

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
(seeded from the module template). On ARMv8-M the kernel's strong
`SVC_Handler`, `PendSV_Handler`, and `SysTick_Handler` override the startup's
weak vectors automatically. On Cortex-M4F, `nsx-freertos` provides strong shim
handlers that route those vectors to FreeRTOS' `vPortSVCHandler`,
`xPortPendSVHandler`, and `xPortSysTickHandler` entry points. No application
handler remapping is needed in either path.

The application also provides the hooks the config enables
(`vApplicationMallocFailedHook`, `vApplicationStackOverflowHook`) in
[src/main.c](src/main.c).

## Build & Run

```bash
# Default board (apollo510_evb)
nsx configure --app-dir .
nsx build     --app-dir .
nsx flash     --app-dir .      # requires JLink + Apollo510 EVB
nsx view      --app-dir .      # opens SWO viewer

# Apollo4P Blue KXR EVB
nsx build     --app-dir . --board apollo4p_blue_kxr_evb
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
SoC's `NSX_SOC_RTOS_PORT_GENERIC` resolves to `ARM_CM55_NTZ` on Apollo510 or
`ARM_CM4F` on Apollo4P, and that the shared application-owned
`FreeRTOSConfig.h` stays aligned with the current SDK template.
