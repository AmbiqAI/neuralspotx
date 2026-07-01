# Role fragment: SoC. SoC fact load + the nsx::soc_flags interface target.
# Apollo4p Blue KXR EVB board descriptor.
#
# Layering contract (see nsx-ambiq-sdk/cmake/README.md):
#   - SoC details (CPU/FPU/ISA/part/capability compile definitions) are owned by
#     the SoC layer. nsx_load_soc_facts("apollo4p") publishes the SoC facts (the
#     single source of truth shared with the SDK's own SoC descriptor) and
#     nsx_soc_flags_target() turns the SoC compile-definition list into
#     nsx::soc_flags (PART_apollo4p, AM_PART_APOLLO4P, ARMCM4, __FPU_PRESENT,
#     NSX_SOC_CORE_M4, NSX_SOC_HAS_*). The board links nsx::soc_flags rather than
#     re-declaring these macros, so the full SoC define set reaches every
#     consumer (nsx::soc_hal, the FreeRTOS port) and cannot drift. A partial
#     hand-rolled copy previously omitted ARMCM4/NSX_SOC_CORE_M4 and silently
#     broke the Cortex-M4 FreeRTOS port.
#   - This board file owns only board details: board name, package, stack, BSP
#     location, and debug/flash defaults.
#
# Both nsx_load_soc_facts() and nsx_soc_flags_target() are provided by the SDK's
# auto-included cmake/nsx_soc_facts.cmake.
nsx_load_soc_facts("apollo4p")

# nsx::soc_flags carries all SoC-owned compile definitions, derived from the SoC
# facts loaded above. Named to match the SDK's own SoC descriptor flags target.
set(NSX_SOC_FLAGS_TARGET nsx_soc_apollo4p_flags)
nsx_soc_flags_target(${NSX_SOC_FLAGS_TARGET})
