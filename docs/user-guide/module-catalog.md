# Module Catalog

The NSX registry ships a curated set of **first-class modules** that cover
SDK integration, platform plumbing, peripherals, profiling, and common runtime
helpers. Every module listed here is discoverable through the CLI and eligible
for `nsx module add` workflows.

```bash
# List the full catalog from your terminal
nsx module list --registry-only
```

!!! tip "Need a module that isn't listed here?"

    NSX supports **custom and third-party modules** alongside the built-in
    catalog. You can register a local directory or any git repo as a module
    for your app — no changes to the upstream registry required.

    See [Custom Modules](custom-modules.md) for registration commands, or
    follow the [Creating a Custom Module](creating-a-custom-module.md)
    walkthrough to build one from scratch.

---

## Quick Filter

Type in the box below to instantly filter the catalog table.

<div>
<input type="text" id="module-filter" class="md-input md-input--stretch" placeholder="Filter modules by name, category, or description…" style="width:100%;padding:.6rem .8rem;margin-bottom:1rem;border:1px solid var(--md-default-fg-color--lightest);border-radius:.4rem;font-size:.88rem;background:var(--md-code-bg-color);color:var(--md-default-fg-color);">
</div>

## All Modules

| Module | Category | Description | SoC Support |
| --- | --- | --- | --- |
| `nsx-core` | :material-cog: Runtime | Core runtime initialization and baseline support for most NSX apps. | All |
| `nsx-harness` | :material-cog: Runtime | Harness-side helpers for logging, smoke tests, and instrumentation-friendly app output. | All |
| `nsx-utils` | :material-cog: Runtime | Shared utility helpers for common runtime tasks. | All |
| `nsx-portable-api` | :material-cog: Runtime | Thin convenience wrappers for migration-friendly app development. | All |
| `nsx-tooling` | :material-wrench: Tooling | CLI-generated app CMake/tooling integration. | All |
| `nsx-soc-hal` | :material-chip: Platform | Shared SoC-level HAL integration layer for NSX targets. | All |
| `nsx-cmsis-startup` | :material-chip: Platform | CMSIS startup integration — vector tables, startup code, early boot wiring. | All |
| `nsx-ambiqsuite-r3` | :material-package-variant: SDK | AmbiqSuite r3 SDK provider for Apollo3 / Apollo3P targets. | Apollo3, 3P |
| `nsx-ambiqsuite-r4` | :material-package-variant: SDK | AmbiqSuite r4 SDK provider for Apollo4L / Apollo4P targets. | Apollo4L, 4P |
| `nsx-ambiqsuite-r5` | :material-package-variant: SDK | AmbiqSuite r5 SDK provider for Apollo5 / Apollo510 / Apollo330P targets. | Apollo5B, 510, 510B, 330P |
| `nsx-ambiq-hal-r3` | :material-package-variant: SDK | Curated HAL wrapper surface for AmbiqSuite r3 targets. | Apollo3, 3P |
| `nsx-ambiq-hal-r4` | :material-package-variant: SDK | Curated HAL wrapper surface for AmbiqSuite r4 targets. | Apollo4L, 4P |
| `nsx-ambiq-hal-r5` | :material-package-variant: SDK | Curated HAL wrapper surface for AmbiqSuite r5 targets. | Apollo5B, 510, 510B, 330P |
| `nsx-ambiq-bsp-r3` | :material-package-variant: SDK | Curated BSP wrapper for board-support on AmbiqSuite r3 targets. | Apollo3, 3P |
| `nsx-ambiq-bsp-r4` | :material-package-variant: SDK | Curated BSP wrapper for board-support on AmbiqSuite r4 targets. | Apollo4L, 4P |
| `nsx-ambiq-bsp-r5` | :material-package-variant: SDK | Curated BSP wrapper for board-support on AmbiqSuite r5 targets. | Apollo5B, 510, 510B, 330P |
| `nsx-peripherals` | :material-expansion-card: Peripheral | Common peripheral-access helpers for board devices and attached hardware. | All |
| `nsx-power` | :material-expansion-card: Peripheral | Power-management helpers — sleep policy, shutdown control, low-power workflows. | All |
| `nsx-uart` | :material-expansion-card: Peripheral | UART wrapper for serial communication, console I/O, and host-device links. | All |
| `nsx-i2c` | :material-expansion-card: Peripheral | I2C wrapper for integrating sensors and peripherals over the I2C bus. | All |
| `nsx-spi` | :material-expansion-card: Peripheral | SPI wrapper for talking to SPI-attached devices and peripherals. | All |
| `nsx-audio` | :material-expansion-card: Peripheral | PDM audio capture driver with DMA-backed sampling and callback delivery. | Apollo5B, 510, 510B |
| `nsx-usb` | :material-expansion-card: Peripheral | USB CDC serial driver using TinyUSB with proper error handling. | Apollo5B, 510, 510B, 4P |
| `nsx-nanopb` | :material-library: Library | Vendored nanopb — zero-dynamic-memory Protocol Buffers in ANSI C. | All |
| `nsx-perf` | :material-speedometer: Profiling | Generic performance measurement helpers for timing and lightweight profiling. | All |
| `nsx-pmu-armv8m` | :material-speedometer: Profiling | Armv8-M PMU helpers for hardware counter configuration, capture, and transport. | Apollo5B, 510, 510B, 330P |

### Board Modules

Board modules are selected automatically when you create an app for a specific
target. They capture board-level wiring and pin configuration.

| Board Module | SoC Family |
| --- | --- |
| `nsx-board-apollo3-evb` | Apollo3 |
| `nsx-board-apollo3-evb-cygnus` | Apollo3 |
| `nsx-board-apollo3p-evb` | Apollo3P |
| `nsx-board-apollo3p-evb-cygnus` | Apollo3P |
| `nsx-board-apollo330mp-evb` | Apollo330P |
| `nsx-board-apollo4l-evb` | Apollo4L |
| `nsx-board-apollo4l-blue-evb` | Apollo4L |
| `nsx-board-apollo4p-evb` | Apollo4P |
| `nsx-board-apollo4p-blue-kbr-evb` | Apollo4P |
| `nsx-board-apollo4p-blue-kxr-evb` | Apollo4P |
| `nsx-board-apollo510-evb` | Apollo510 |
| `nsx-board-apollo510b-evb` | Apollo510B |
| `nsx-board-apollo5b-evb` | Apollo5B |

---

## Working with Modules

### Add a module to your app

```bash
nsx module add nsx-peripherals --app-dir my-app
```

NSX resolves the full dependency closure, validates board/SoC compatibility,
and vendors the module into `my-app/modules/`.

### Inspect a module

```bash
nsx module describe nsx-audio
```

### Search by keyword

```bash
nsx module search "uart serial"
```

### Remove a module

```bash
nsx module remove nsx-peripherals --app-dir my-app
```

---

## Related Pages

- [Modules Overview](modules.md) — terminology and CLI workflows
- [Custom Modules](custom-modules.md) — register third-party or local modules
- [Creating a Custom Module](creating-a-custom-module.md) — step-by-step walkthrough
- [First-Class Modules](first-class-modules.md) — detailed family descriptions
- [Module Model](../architecture/module-model.md) — architecture deep-dive

<script>
document.addEventListener("DOMContentLoaded", function () {
  var input = document.getElementById("module-filter");
  if (!input) return;
  input.addEventListener("input", function () {
    var term = this.value.toLowerCase();
    document.querySelectorAll(".md-content table").forEach(function (table) {
      var rows = table.querySelectorAll("tbody tr");
      rows.forEach(function (row) {
        var text = row.textContent.toLowerCase();
        row.style.display = text.includes(term) ? "" : "none";
      });
    });
  });
});
</script>
