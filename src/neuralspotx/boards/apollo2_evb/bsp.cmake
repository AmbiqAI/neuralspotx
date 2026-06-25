# Role fragment: BSP. SDK provider precondition + AmbiqSuite BSP/MCU/HAL locations.
if(NOT NSX_SDK_PROVIDER STREQUAL "ambiqsuite")
    message(FATAL_ERROR
        "apollo2_evb requires NSX_SDK_PROVIDER=ambiqsuite, got '${NSX_SDK_PROVIDER}'."
    )
endif()

set(NSX_AMBIQ_BOARD_NAME "apollo2_evb")
set(NSX_AMBIQ_PART_NAME "apollo2")
set(NSX_AMBIQ_BSP_LIB_SUBDIR "apollo2_evb")
set(NSX_AMBIQ_BSP_DIR "${NSX_AMBIQSUITE_ROOT}/boards/${NSX_AMBIQ_BOARD_NAME}/bsp")
set(NSX_AMBIQ_MCU_DIR "${NSX_AMBIQSUITE_ROOT}/mcu/${NSX_AMBIQ_PART_NAME}")
set(NSX_AMBIQ_HAL_DIR "${NSX_AMBIQ_MCU_DIR}/hal")
# apollo2/apollo3 parts ship a flat hal/ (no hal/mcu subtree), so
# NSX_AMBIQ_HAL_MCU_DIR is intentionally left unset; the HAL module guards it
# with if(DEFINED ...).

# BSP capability facts: buttons (consumed by nsx-ambiq-bsp -> nsx::bsp).
set(NSX_BOARD_HAS_BUTTONS TRUE)
set(NSX_BOARD_BUTTON_COUNT 3)
set(NSX_BOARD_BUTTON_PINS
    AM_BSP_GPIO_BUTTON0
    AM_BSP_GPIO_BUTTON1
    AM_BSP_GPIO_BUTTON2
)
