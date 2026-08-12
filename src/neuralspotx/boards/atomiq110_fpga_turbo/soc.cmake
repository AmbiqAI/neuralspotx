# Role fragment: SoC. SoC fact load + the nsx::soc_flags interface target.
nsx_load_soc_facts("atomiq110")

set(NSX_SOC_FLAGS_TARGET nsx_soc_atomiq110_flags)
nsx_soc_flags_target(${NSX_SOC_FLAGS_TARGET})