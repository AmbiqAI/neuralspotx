# SEGGER configuration for Apollo4P family.
#
# NSX_SEGGER_CPUFREQ is the TPIU *trace clock*, NOT the CPU clock.
# On Apollo4P the BSP configures the trace clock to HFRC_96MHz.
set(NSX_SEGGER_DEVICE "AMAP42KK-KBR")
set(NSX_SEGGER_IF_SPEED "4000")
set(NSX_SEGGER_PF_ADDR "0x18000")
set(NSX_SEGGER_CPUFREQ "96000000")
set(NSX_SEGGER_SWOFREQ "1000000")
