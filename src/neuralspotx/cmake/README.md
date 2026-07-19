# NSX CMake Support

This directory contains the CMake support files packaged with `neuralspotx`.
Configured apps copy these files into their app-local `cmake/nsx/` directory,
so the generated project keeps an explicit, reproducible tooling snapshot.

Key contents include:

- `nsx_helpers.cmake` for app bootstrap, target finalization, and flash recipes;
- `nsx_sdk_providers.cmake` for SDK-provider selection;
- `segger/` J-Link templates and SoC defaults; and
- CMake package configuration templates.

Keep these files compatible with the app-local vendoring model and include
them in package-data and wheel smoke tests when the packaged layout changes.
