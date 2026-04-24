cmake_minimum_required(VERSION 3.24)
project(power_benchmark LANGUAGES C CXX ASM)

set(NSX_BOARD "apollo510_evb" CACHE STRING "Target board")

include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/modules.cmake)
include(${CMAKE_CURRENT_LIST_DIR}/cmake/nsx/nsx_app_bootstrap.cmake)

nsx_bootstrap_app(
    APP_ROOT "${CMAKE_CURRENT_LIST_DIR}"
    BOARD "${NSX_BOARD}"
    MODULES ${NSX_APP_MODULES}
)

# ---------------------------------------------------------------------------
# Benchmark Mode: coremark | while1 | deepsleep
# ---------------------------------------------------------------------------
set(BENCHMARK_MODE "coremark" CACHE STRING "Benchmark: coremark, coremark_nvm, coremark_minmem, coremark_sdk5, while1, deepsleep")
option(BENCHMARK_HP_MODE "Run at HP 250 MHz instead of LP 96 MHz" OFF)
option(USE_ARMCLANG "Compile CoreMark hot-path with armclang -Ofast" OFF)

# ---------------------------------------------------------------------------
# CoreMark sources (only for coremark mode)
# ---------------------------------------------------------------------------
set(COREMARK_DIR ${CMAKE_CURRENT_LIST_DIR}/src/coremark)

set(APP_SOURCES src/main.c)
set(APP_DEFINES "")

if(BENCHMARK_MODE STREQUAL "coremark" OR BENCHMARK_MODE STREQUAL "coremark_nvm" OR BENCHMARK_MODE STREQUAL "coremark_minmem" OR BENCHMARK_MODE STREQUAL "coremark_sdk5")
    list(APPEND APP_DEFINES BENCHMARK_COREMARK)
    if(BENCHMARK_MODE STREQUAL "coremark_nvm")
        list(APPEND APP_DEFINES BENCHMARK_NVM_ALL_ON)
    elseif(BENCHMARK_MODE STREQUAL "coremark_minmem")
        list(APPEND APP_DEFINES BENCHMARK_NVM_MINMEM)
    elseif(BENCHMARK_MODE STREQUAL "coremark_sdk5")
        list(APPEND APP_DEFINES BENCHMARK_SDK5_MIMIC)
    endif()
    list(APPEND APP_SOURCES src/core_portme.c)

    if(USE_ARMCLANG)
        # --- armclang cross-compilation for CoreMark hot-path ---
        set(ARMCLANG "/Applications/ARMClangToolchain/6.24Rel19/bin/armclang")
        set(ARMCLANG_FLAGS
            --target=arm-arm-none-eabi -mcpu=cortex-m55 -mfloat-abi=hard
            -Ofast -fno-builtin -fshort-enums
            -I${CMAKE_CURRENT_LIST_DIR}/src -I${COREMARK_DIR}
            -DPERFORMANCE_RUN=1 -DITERATIONS=0 "-DFLAGS_STR=\\\"armclang\\\""
            -Dmain=coremark_main
        )
        set(ARMCLANG_COREMARK_FILES
            core_main.c core_list_join.c core_matrix.c core_state.c core_util.c)
        set(COREMARK_OBJS "")
        foreach(src ${ARMCLANG_COREMARK_FILES})
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
    else()
        # --- GCC compilation for CoreMark ---
        list(APPEND APP_SOURCES
            ${COREMARK_DIR}/core_main.c
            ${COREMARK_DIR}/core_list_join.c
            ${COREMARK_DIR}/core_matrix.c
            ${COREMARK_DIR}/core_state.c
            ${COREMARK_DIR}/core_util.c
        )
    endif()

elseif(BENCHMARK_MODE STREQUAL "deepsleep")
    list(APPEND APP_DEFINES BENCHMARK_DEEPSLEEP)

elseif(BENCHMARK_MODE STREQUAL "while1")
    # No extra defines — while1 is the default fallthrough in main.c

else()
    message(FATAL_ERROR "Unknown BENCHMARK_MODE: ${BENCHMARK_MODE}. Use: coremark, coremark_nvm, coremark_minmem, coremark_sdk5, while1, deepsleep")
endif()

# ---------------------------------------------------------------------------
# Executable
# ---------------------------------------------------------------------------
add_executable(power_benchmark ${APP_SOURCES})

if((BENCHMARK_MODE STREQUAL "coremark" OR BENCHMARK_MODE STREQUAL "coremark_nvm" OR BENCHMARK_MODE STREQUAL "coremark_minmem" OR BENCHMARK_MODE STREQUAL "coremark_sdk5") AND USE_ARMCLANG)
    target_link_libraries(power_benchmark PRIVATE ${COREMARK_OBJS})
    add_dependencies(power_benchmark armclang_coremark_objs)
endif()

target_include_directories(power_benchmark PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
    ${COREMARK_DIR}
)

target_compile_definitions(power_benchmark PRIVATE
    ${APP_DEFINES}
    $<$<BOOL:${BENCHMARK_HP_MODE}>:BENCHMARK_HP_MODE>
)

# CoreMark-specific defines (only when mode=coremark, only on CoreMark files)
if((BENCHMARK_MODE STREQUAL "coremark" OR BENCHMARK_MODE STREQUAL "coremark_nvm" OR BENCHMARK_MODE STREQUAL "coremark_minmem" OR BENCHMARK_MODE STREQUAL "coremark_sdk5") AND NOT USE_ARMCLANG)
    foreach(_cm_src core_main.c core_list_join.c core_matrix.c core_state.c core_util.c)
        set_source_files_properties(${COREMARK_DIR}/${_cm_src} PROPERTIES
            COMPILE_DEFINITIONS "main=coremark_main;PERFORMANCE_RUN=1;ITERATIONS=0;FLAGS_STR=\"${CMAKE_C_FLAGS}\""
        )
    endforeach()
    set_source_files_properties(src/core_portme.c PROPERTIES
        COMPILE_DEFINITIONS "main=coremark_main;PERFORMANCE_RUN=1;ITERATIONS=0;FLAGS_STR=\"${CMAKE_C_FLAGS}\""
    )
endif()

target_link_libraries(power_benchmark PRIVATE
    nsx::board
    nsx::runtime_core
    nsx::power
)

# ---------------------------------------------------------------------------
# coremark_minmem: strip -ffast-math to match SDK5 -O3-only build.
# GCC flags are last-wins, and the toolchain interface target appends after
# the target's own options.  Remove it from the source (the flags target).
# ---------------------------------------------------------------------------
if(BENCHMARK_MODE STREQUAL "coremark_minmem" OR BENCHMARK_MODE STREQUAL "coremark_sdk5")
    get_target_property(_tc_opts nsx_board_apollo510_evb_flags INTERFACE_COMPILE_OPTIONS)
    if(_tc_opts)
        list(REMOVE_ITEM _tc_opts "-ffast-math")
        set_property(TARGET nsx_board_apollo510_evb_flags PROPERTY INTERFACE_COMPILE_OPTIONS ${_tc_opts})
    endif()
endif()

# ---------------------------------------------------------------------------
# ITCM linker script (coremark and while1 modes use ITCM execution)
# coremark_nvm runs from NVM — use the default board linker script.
# ---------------------------------------------------------------------------
if(NOT BENCHMARK_MODE STREQUAL "deepsleep" AND NOT BENCHMARK_MODE STREQUAL "coremark_nvm" AND NOT BENCHMARK_MODE STREQUAL "coremark_minmem" AND NOT BENCHMARK_MODE STREQUAL "coremark_sdk5")
    if(NSX_TOOLCHAIN_FAMILY STREQUAL "armclang")
        # TODO: create an armclang scatter file for ITCM placement
        message(STATUS "Skipping ITCM linker-script override for armclang (not yet ported)")
    else()
        set(PB_LINKER_SCRIPT "${CMAKE_CURRENT_LIST_DIR}/linker_script_itcm.ld")
        get_target_property(_board_link_opts nsx_board_apollo510_evb_flags INTERFACE_LINK_OPTIONS)
        list(FILTER _board_link_opts EXCLUDE REGEX "^-T")
        list(APPEND _board_link_opts "-T${PB_LINKER_SCRIPT}")
        set_property(TARGET nsx_board_apollo510_evb_flags PROPERTY INTERFACE_LINK_OPTIONS ${_board_link_opts})
    endif()
endif()

nsx_finalize_app(power_benchmark)
