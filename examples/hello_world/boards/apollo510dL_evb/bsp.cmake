# Role fragment: BSP. SDK provider precondition + AmbiqSuite BSP/MCU/HAL locations.
if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite")
    message(FATAL_ERROR
        "apollo510dL_evb requires NSX_SDK_PROVIDER=ambiqsuite, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo510dL_evb")
set(NSX_AMBIQ_PART_NAME "apollo510L")
set(NSX_AMBIQ_BSP_LIB_SUBDIR "apollo510dL_evb")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
set(NSX_AMBIQ_HAL_MCU_DIR "${NSX_AMBIQ_HAL_DIR}/mcu")

# BSP capability facts: buttons (consumed by nsx-ambiq-bsp -> nsx::bsp).
set(NSX_BOARD_HAS_BUTTONS TRUE)
set(NSX_BOARD_BUTTON_COUNT 2)
set(NSX_BOARD_BUTTON_PINS
    AM_BSP_GPIO_BUTTON0
    AM_BSP_GPIO_BUTTON1
)
