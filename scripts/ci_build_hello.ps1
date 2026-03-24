$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $PSScriptRoot

cmake --preset ap3p-gcc-ninja-windows -S $RootDir -B "$RootDir/build/ap3p-gcc-ninja"
cmake --build --preset build-ap3p-windows
