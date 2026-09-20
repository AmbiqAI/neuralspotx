Run this before creating an app, and first when flash or view problems suggest a local tool
issue rather than an app issue.

It checks Python availability, `uv`, CMake, Ninja, the Arm GNU toolchain
(`arm-none-eabi-gcc`), `JLinkExe`, `JLinkSWOViewerCL` and basic SEGGER J-Link runtime
startup. Arm Compiler for Embedded (`armclang`, `armlink`, `fromelf`) and Arm Toolchain for
Embedded (`$ATFE_ROOT/bin/clang`, `llvm-objcopy`, picolibc newlib config) are checked as
optional.

`doctor` checks that the tools are installed and can start. It does not require a connected
target board. If SEGGER runtime startup fails, fix that before debugging `nsx flash` or
`nsx view`.
