# Role fragment: SoC. SoC fact load + the nsx::soc_flags interface target.
# SoC facts (NSX_SOC_* + NSX_CPU/NSX_FPU/NSX_FLOAT_ABI/NSX_ABI_FLAGS) come from
# the nsx-ambiq-sdk single source of truth so they cannot drift from the SDK's
# own SoC descriptor. This also publishes the RTOS port facts the optional
# nsx-freertos module consumes. nsx_load_soc_facts() is provided by the SDK's
# auto-included cmake/nsx_soc_facts.cmake.
nsx_load_soc_facts("apollo3p")

# nsx::soc_flags carries all SoC-owned compile definitions, derived from the
# SoC facts loaded above. Named to match the SDK's own SoC descriptor flags
# target. The board links it below rather than re-declaring SoC macros.
set(NSX_SOC_FLAGS_TARGET nsx_soc_apollo3p_flags)
nsx_soc_flags_target(${NSX_SOC_FLAGS_TARGET})
