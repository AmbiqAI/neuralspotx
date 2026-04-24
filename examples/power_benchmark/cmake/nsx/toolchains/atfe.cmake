# Arm Toolchain for Embedded (ATfE) — LLVM-based bare-metal toolchain.
#
# Uses:
#   - clang          as the C/C++/ASM compiler
#   - lld (via clang driver) as the linker (GNU ld-compatible, takes .ld scripts)
#   - llvm-ar        as the archiver
#   - llvm-objcopy   for binary generation
#   - llvm-size      for size reporting
#
# Requires ATfE with the newlib overlay installed.
# Set ATFE_ROOT env var to the ATfE install dir so that find_program picks up
# ATfE's clang rather than macOS system clang.
#
# See https://github.com/arm/arm-toolchain

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

# Locate ATfE tools.  ATFE_ROOT env var is the recommended way to
# disambiguate from macOS Xcode clang.
if(DEFINED ENV{ATFE_ROOT})
    set(_atfe_hints "$ENV{ATFE_ROOT}/bin")
else()
    message(WARNING
        "ATFE_ROOT is not set.  find_program may pick up macOS system clang. "
        "Set ATFE_ROOT to the ATfE install directory.")
endif()

find_program(ATFE_CLANG   clang        HINTS ${_atfe_hints} NO_DEFAULT_PATH REQUIRED)
find_program(ATFE_CLANGXX clang++      HINTS ${_atfe_hints} NO_DEFAULT_PATH REQUIRED)
find_program(ATFE_AR      llvm-ar      HINTS ${_atfe_hints} NO_DEFAULT_PATH REQUIRED)
find_program(ATFE_OBJCOPY llvm-objcopy HINTS ${_atfe_hints} NO_DEFAULT_PATH REQUIRED)
find_program(ATFE_SIZE    llvm-size    HINTS ${_atfe_hints} NO_DEFAULT_PATH REQUIRED)

set(CMAKE_C_COMPILER   ${ATFE_CLANG})
set(CMAKE_CXX_COMPILER ${ATFE_CLANGXX})
set(CMAKE_ASM_COMPILER ${ATFE_CLANG})
set(CMAKE_AR           ${ATFE_AR})
set(CMAKE_OBJCOPY      ${ATFE_OBJCOPY})
set(CMAKE_SIZE         ${ATFE_SIZE})

set(CMAKE_EXECUTABLE_SUFFIX ".elf")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

# Tell clang to target arm-none-eabi and use the newlib overlay.
# --config=newlib.cfg switches the sysroot to lib/clang-runtimes/newlib.
add_compile_options(--target=arm-none-eabi --config=newlib.cfg)
add_link_options(--target=arm-none-eabi --config=newlib.cfg -fuse-ld=lld)
