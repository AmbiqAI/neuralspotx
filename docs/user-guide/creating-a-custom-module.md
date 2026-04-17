# Creating a Custom Module

This walkthrough shows how to generate a new NSX module skeleton with the CLI,
review the files it creates, register it for your app, and build with it.
By the end you'll have a working module with the correct metadata, CMake
target, and dependency wiring.

---

## 1. Generate the Skeleton

Use `nsx module init` as the starting point for new custom modules.

```bash
nsx module init my-sensor-driver \
  --type backend_specific \
  --summary "I2C driver for the XYZ ambient light sensor." \
  --dependency nsx-core \
  --dependency nsx-i2c \
  --soc apollo510 \
  --soc apollo510b \
  --soc apollo5b
```

This produces a standard layout:

```
my-sensor-driver/
├── CMakeLists.txt
├── README.md
├── nsx-module.yaml
├── includes-api/
│   └── my_sensor_driver/
│       └── my_sensor_driver.h
└── src/
    └── my_sensor_driver.c
```

Key flags:

- `--type` sets `module.type` in the generated metadata.
- `--dependency` adds required module dependencies and matching CMake links.
- `--soc`, `--board`, and `--toolchain` seed compatibility constraints.
- `--name` lets you decouple the logical module name from the directory name.
- `--force` lets you write into a non-empty destination directory.

---

## 2. Review the Generated Metadata

Generated `my-sensor-driver/nsx-module.yaml`:

```yaml
schema_version: 1

module:
  name: my-sensor-driver
  type: backend_specific      # (1)!
  version: "0.1.0"

support:
  ambiqsuite: true
  zephyr: false

summary: "I2C driver for the XYZ ambient light sensor."

capabilities: []
use_cases: []
agent_keywords: []

build:
  cmake:
    package: my_sensor_driver              # (2)!
    targets:
      - nsx::my_sensor_driver              # (3)!

depends:
  required:
    - nsx-core
    - nsx-i2c                              # (4)!
  optional: []

compatibility:
  boards:
    - "*"                                  # (5)!
  socs:
    - "apollo510"
    - "apollo510b"
    - "apollo5b"
  toolchains:
    - "arm-none-eabi-gcc"
```

The init command fills in a valid baseline and derives:

- `build.cmake.package` from the module name (`my_sensor_driver`)
- `build.cmake.targets` from the module name (`nsx::my_sensor_driver`)
- dependency lists from repeated `--dependency` flags
- compatibility lists from `--board`, `--soc`, and `--toolchain`

1. `backend_specific` means the implementation varies per SoC/platform.
   Use `runtime` for portable code with no hardware dependencies.
2. The `find_package()` name your app's CMake will use.
3. Namespaced CMake target. Apps link against this.
4. Declare any built-in modules your driver depends on.
5. `"*"` allows all boards. List specific board names to restrict.

---

## 3. Review the Generated Build Files

Generated `my-sensor-driver/CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.20)

find_package(nsx_core REQUIRED)
find_package(nsx_i2c REQUIRED)

add_library(my_sensor_driver STATIC
  src/my_sensor_driver.c
)

target_include_directories(my_sensor_driver PUBLIC
  includes-api
)

target_link_libraries(my_sensor_driver PUBLIC
  ${NSX_BOARD_FLAGS_TARGET}
  nsx::core
  nsx::i2c
)

add_library(nsx::my_sensor_driver ALIAS my_sensor_driver)
```

Key rules:

- The library name must match `build.cmake.package` in the YAML.
- The alias must match the `build.cmake.targets` entry.
- Link against `${NSX_BOARD_FLAGS_TARGET}` plus any dependency targets.

The scaffold also generates a public header and source stub:

**`includes-api/my_sensor_driver/my_sensor_driver.h`**

```c
#ifndef MY_SENSOR_DRIVER_H
#define MY_SENSOR_DRIVER_H

int my_sensor_driver_init(void);
int my_sensor_driver_run(void);

#endif
```

**`src/my_sensor_driver.c`**

```c
#include "my_sensor_driver/my_sensor_driver.h"

int my_sensor_driver_init(void) {
    return 0;
}

int my_sensor_driver_run(void) {
    return 0;
}
```

---

## 4. Validate the Generated Module

Before registering it, validate the generated metadata:

```bash
nsx module validate my-sensor-driver/nsx-module.yaml
```

---

## 5. Register with Your App

Register the module from a local filesystem path:

```bash
nsx module register my-sensor-driver \
  --metadata ./my-sensor-driver/nsx-module.yaml \
  --project my_sensor_driver \
  --project-local-path ./my-sensor-driver \
  --app-dir my-app
```

This updates `my-app/nsx.yml` with a custom module entry that points to your
local directory.

Alternatively, if your module lives in a git repo:

```bash
nsx module register my-sensor-driver \
  --metadata modules/my-sensor-driver/nsx-module.yaml \
  --project my_sensor_driver \
  --project-url https://github.com/yourorg/my-sensor-driver.git \
  --project-revision main \
  --app-dir my-app
```

---

## 6. Add and Build

Now add the module to your app and build:

```bash
# Enable the module (resolves deps, vendors into app/modules/)
nsx module add my-sensor-driver --app-dir my-app

# Build
nsx build --app-dir my-app
```

The module is vendored into `my-app/modules/my-sensor-driver/` alongside any
built-in modules the app already uses.

---

## 7. Replace the Stubs with Real Code

The scaffolded source and header are intentionally minimal. Replace the stub
functions with your real driver or runtime implementation once the module has
the right dependency and compatibility shape.

For example, a sensor driver would typically:

- add the real dependency set with `--dependency` flags when scaffolding
- replace `my_sensor_driver_init()` with hardware bring-up
- add a richer public API under `includes-api/`
- extend `README.md` with usage and integration notes

---

## 8. Use It in Your App Code

In your app's `main.c`:

```c
#include "my_sensor_driver/my_sensor_driver.h"

int main(void) {
    my_sensor_driver_init();
    my_sensor_driver_run();
    return 0;
}
```

In your app's `CMakeLists.txt`, link the target:

```cmake
find_package(my_sensor_driver REQUIRED)
target_link_libraries(my_app PRIVATE nsx::my_sensor_driver)
```

---

## Summary

| Step | What happens |
| --- | --- |
| Generate skeleton | `nsx module init` writes the standard layout |
| Review metadata | Confirm identity, deps, compatibility, and build targets |
| Review build files | Confirm library, includes, alias, and dependency links |
| Validate | `nsx module validate` checks schema and references |
| Register | `nsx module register` adds to app-local config |
| Add and build | `nsx module add` vendors; `nsx build` compiles |

---

## Related Pages

- [Module Catalog](module-catalog.md) — browse all built-in modules
- [Custom Modules](custom-modules.md) — registration commands and metadata schema
- [Adding Modules](../contributing/adding-modules.md) — contributing modules to the registry
- [Module Model](../architecture/module-model.md) — architecture deep-dive
