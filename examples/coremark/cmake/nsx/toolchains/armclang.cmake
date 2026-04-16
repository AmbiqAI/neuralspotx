# Arm Compiler 6 (armclang) CMake toolchain file for NSX bare-metal targets.
#
# armclang uses:
#   - armclang   as the C/C++/ASM compiler
#   - armlink    as the linker (scatter-file based)
#   - armar      as the archiver
#   - fromelf    as the binary utility (replaces objcopy + size)

set(CMAKE_SYSTEM_NAME Generic)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

find_program(ARMCLANG armclang REQUIRED)
find_program(ARMLINK armlink REQUIRED)
find_program(ARMAR armar REQUIRED)
find_program(FROMELF fromelf REQUIRED)

set(CMAKE_C_COMPILER ${ARMCLANG})
set(CMAKE_CXX_COMPILER ${ARMCLANG})
set(CMAKE_ASM_COMPILER ${ARMCLANG})
set(CMAKE_AR ${ARMAR})
set(CMAKE_LINKER ${ARMLINK})

# fromelf serves as both objcopy and size replacement
set(CMAKE_OBJCOPY ${FROMELF})
set(CMAKE_SIZE ${FROMELF})

set(CMAKE_EXECUTABLE_SUFFIX ".elf")

# armclang bundles its own runtime — no standard library flags needed.
set(CMAKE_C_STANDARD_LIBRARIES "")
set(CMAKE_CXX_STANDARD_LIBRARIES "")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS ON)

# Tell CMake to use armlink directly for the final link step.
# By default CMake tries to invoke the compiler as a linker driver,
# which does not work well with armlink's scatter-file syntax.
set(CMAKE_C_LINK_EXECUTABLE
    "<CMAKE_LINKER> <LINK_FLAGS> <OBJECTS> <LINK_LIBRARIES> -o <TARGET>")
set(CMAKE_CXX_LINK_EXECUTABLE
    "<CMAKE_LINKER> <LINK_FLAGS> <OBJECTS> <LINK_LIBRARIES> -o <TARGET>")
