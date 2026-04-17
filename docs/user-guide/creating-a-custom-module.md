# Creating a Custom Module

This walkthrough shows how to create a new NSX module from scratch, register
it for your app, and build with it. By the end you'll have a working module
with the correct metadata, CMake target, and dependency wiring.

---

## 1. Scaffold the Directory

Create a directory for your module with the standard layout:

```
my-sensor-driver/
├── nsx-module.yaml          # Module metadata (required)
├── CMakeLists.txt            # Build definition (required)
├── includes-api/
│   └── my_sensor_driver/
│       └── my_sensor_driver.h
└── src/
    └── my_sensor_driver.c
```

```bash
mkdir -p my-sensor-driver/{includes-api/my_sensor_driver,src}
```

---

## 2. Write the Module Metadata

Create `my-sensor-driver/nsx-module.yaml`:

```yaml
schema_version: 1

module:
  name: my-sensor-driver
  type: backend_specific      # (1)!
  version: "0.1.0"

support:
  ambiqsuite: true
  zephyr: false

summary: I2C driver for the XYZ ambient light sensor.

capabilities:
  - ambient_light_sensing

use_cases:
  - Read ambient light levels over I2C from the XYZ sensor

agent_keywords:
  - sensor
  - i2c
  - light
  - ambient

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
    - apollo510
    - apollo510b
    - apollo5b
  toolchains:
    - arm-none-eabi-gcc
```

1. `backend_specific` means the implementation varies per SoC/platform.
   Use `runtime` for portable code with no hardware dependencies.
2. The `find_package()` name your app's CMake will use.
3. Namespaced CMake target. Apps link against this.
4. Declare any built-in modules your driver depends on.
5. `"*"` allows all boards. List specific board names to restrict.

!!! info "Validate before registering"

    ```bash
    nsx module validate my-sensor-driver/nsx-module.yaml
    ```

    This checks required fields, dependency references, and schema version.

---

## 3. Write the CMakeLists.txt

Create `my-sensor-driver/CMakeLists.txt`:

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
  nsx::core
  nsx::i2c
)

add_library(nsx::my_sensor_driver ALIAS my_sensor_driver)
```

Key rules:

- The library name must match `build.cmake.package` in the YAML.
- The alias must match the `build.cmake.targets` entry.
- Link against dependency targets declared in `depends.required`.

---

## 4. Write a Minimal Implementation

**`includes-api/my_sensor_driver/my_sensor_driver.h`**

```c
#ifndef MY_SENSOR_DRIVER_H
#define MY_SENSOR_DRIVER_H

#include <stdint.h>

/// Initialize the XYZ ambient light sensor on the given I2C bus.
int my_sensor_init(uint32_t i2c_module);

/// Read the current ambient light level in lux.
int my_sensor_read_lux(float *lux_out);

#endif
```

**`src/my_sensor_driver.c`**

```c
#include "my_sensor_driver/my_sensor_driver.h"
#include "ns_i2c.h"

static uint32_t g_i2c_handle;

int my_sensor_init(uint32_t i2c_module) {
    g_i2c_handle = i2c_module;
    // TODO: send configuration sequence to sensor
    return 0;
}

int my_sensor_read_lux(float *lux_out) {
    // TODO: read sensor register over I2C and convert to lux
    *lux_out = 0.0f;
    return 0;
}
```

---

## 5. Register with Your App

Register the module from a local filesystem path:

```bash
nsx module register my-sensor-driver \
  --metadata ./my-sensor-driver/nsx-module.yaml \
  --project my_sensor_repo \
  --project-local-path ./my-sensor-driver \
  --app-dir my-app
```

This updates `my-app/nsx.yml` with a custom module entry that points to your
local directory.

Alternatively, if your module lives in a git repo:

```bash
nsx module register my-sensor-driver \
  --metadata modules/my-sensor-driver/nsx-module.yaml \
  --project my_sensor_repo \
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

## 7. Use It in Your App Code

In your app's `main.c`:

```c
#include "my_sensor_driver/my_sensor_driver.h"

int main(void) {
    my_sensor_init(0);

    float lux;
    my_sensor_read_lux(&lux);

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
| Create directory | Standard layout with `nsx-module.yaml` + `CMakeLists.txt` |
| Write metadata | Declare identity, deps, compatibility, build targets |
| Write CMake | Define library, includes, link deps, create alias |
| Validate | `nsx module validate` checks schema and references |
| Register | `nsx module register` adds to app-local config |
| Add and build | `nsx module add` vendors; `nsx build` compiles |

---

## Related Pages

- [Module Catalog](module-catalog.md) — browse all built-in modules
- [Custom Modules](custom-modules.md) — registration commands and metadata schema
- [Adding Modules](../contributing/adding-modules.md) — contributing modules to the registry
- [Module Model](../architecture/module-model.md) — architecture deep-dive
