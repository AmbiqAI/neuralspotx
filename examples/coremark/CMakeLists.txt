cmake_minimum_required(VERSION 3.24)
project(coremark LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

# ---------------------------------------------------------------------------
# CoreMark sources (EEMBC, Apache-2.0)
# ---------------------------------------------------------------------------
set(COREMARK_DIR ${CMAKE_CURRENT_LIST_DIR}/src/coremark)

option(USE_ARMCLANG_COREMARK "Compile CoreMark hot-path with armclang -Ofast" OFF)
option(COREMARK_HP_MODE "Run CoreMark at HP 250 MHz instead of LP 96 MHz" OFF)
option(COREMARK_SCORE_ONLY "Only print score, skip power measurement loop" OFF)

if(USE_ARMCLANG_COREMARK)
    # Pre-compile CoreMark sources with armclang for better codegen
    set(ARMCLANG "/Applications/ARMClangToolchain/6.24Rel19/bin/armclang")
    set(ARMCLANG_FLAGS
        --target=arm-arm-none-eabi -mcpu=cortex-m55 -mfloat-abi=hard
        -Ofast -fno-builtin -fshort-enums
        ${ARMCLANG_EXTRA_FLAGS}
        -I${CMAKE_CURRENT_LIST_DIR}/src -I${COREMARK_DIR}
        -DPERFORMANCE_RUN=1 -DITERATIONS=0 "-DFLAGS_STR=\\\"armclang\\\""
    )

    # ARMCLANG_FILES: semicolon-separated list of which files to compile with armclang.
    # All others compiled with GCC.  Default: all 5 CoreMark files.
    set(ALL_COREMARK core_main.c core_list_join.c core_matrix.c core_state.c core_util.c)
    if(ARMCLANG_FILES)
        set(ARMCLANG_SRCS ${ARMCLANG_FILES})
    else()
        set(ARMCLANG_SRCS ${ALL_COREMARK})
    endif()
    set(GCC_SRCS "")
    foreach(f ${ALL_COREMARK})
        list(FIND ARMCLANG_SRCS ${f} _idx)
        if(_idx EQUAL -1)
            list(APPEND GCC_SRCS ${COREMARK_DIR}/${f})
        endif()
    endforeach()

    set(COREMARK_OBJS "")
    foreach(src ${ARMCLANG_SRCS})
        get_filename_component(base ${src} NAME_WE)
        set(obj ${CMAKE_CURRENT_BINARY_DIR}/armclang_objs/${base}.o)
        add_custom_command(
            OUTPUT ${obj}
            COMMAND ${CMAKE_COMMAND} -E make_directory ${CMAKE_CURRENT_BINARY_DIR}/armclang_objs
            COMMAND ${ARMCLANG} ${ARMCLANG_FLAGS} -c ${COREMARK_DIR}/${src} -o ${obj}
            DEPENDS ${COREMARK_DIR}/${src} ${CMAKE_CURRENT_LIST_DIR}/src/core_portme.h
            COMMENT "armclang: ${src}"
        )
        list(APPEND COREMARK_OBJS ${obj})
    endforeach()
    add_custom_target(armclang_coremark_objs DEPENDS ${COREMARK_OBJS})

    add_executable(coremark
        # Platform port (NSX) — compiled with GCC
        src/core_portme.c
        # Any CoreMark files compiled with GCC
        ${GCC_SRCS}
    )
    target_link_libraries(coremark PRIVATE ${COREMARK_OBJS})
    add_dependencies(coremark armclang_coremark_objs)
else()
    add_executable(coremark
        # CoreMark core (upstream EEMBC)
        ${COREMARK_DIR}/core_main.c
        ${COREMARK_DIR}/core_list_join.c
        ${COREMARK_DIR}/core_matrix.c
        ${COREMARK_DIR}/core_state.c
        ${COREMARK_DIR}/core_util.c
        # Platform port (NSX)
        src/core_portme.c
    )
endif()

target_include_directories(coremark PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src          # core_portme.h
    ${COREMARK_DIR}                        # coremark.h
)

# Compiler flags string for CoreMark reporting
target_compile_definitions(coremark PRIVATE
    FLAGS_STR="${CMAKE_C_FLAGS}"
    ITERATIONS=0                           # auto-calibrate
    PERFORMANCE_RUN=1
    $<$<BOOL:${COREMARK_HP_MODE}>:COREMARK_HP_MODE>
    $<$<BOOL:${COREMARK_SCORE_ONLY}>:COREMARK_SCORE_ONLY>
)

target_link_libraries(coremark PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::power
)

# ---------------------------------------------------------------------------
# Override linker script: run ALL .text/.rodata from ITCM (zero-wait-state)
# Strip the board-default linker-script flag and replace with our ITCM variant.
# ---------------------------------------------------------------------------
if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
    # TODO: create an armclang scatter file for ITCM placement
    message(STATUS "Skipping ITCM linker-script override for armclang (not yet ported)")
else()
    set(COREMARK_LINKER_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/linker_script_itcm.ld")
    get_target_property(_board_link_opts nsx_board_apollo510_evb_flags INTERFACE_LINK_OPTIONS)
    list(FILTER _board_link_opts EXCLUDE REGEX "^-T")
    list(APPEND _board_link_opts "-T${COREMARK_LINKER_SCRIPT}")
    set_property(TARGET nsx_board_apollo510_evb_flags PROPERTY INTERFACE_LINK_OPTIONS ${_board_link_opts})
endif()

nsx_finalize_app(coremark)
