# NSX Tooling CMake Boundary

This directory is the temporary in-place tooling boundary for split-repo work.

Current status:
- Used in-place from `src/neuralspotx/cmake`.
- Maintained as a nested local git repo during migration.
- Planned to become the standalone `nsx-tooling` repo boundary.

Key contents:
- `nsx_helpers.cmake`
- `nsx_sdk_providers.cmake`
- `segger/` templates and SoC defaults
- package config templates
