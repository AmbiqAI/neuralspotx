# SEGGER configuration for Apollo2 family.
#
# NSX_SEGGER_CPUFREQ is the TPIU *trace clock*, NOT the CPU clock.
# On Apollo2 the trace clock is 48 MHz (HFRC).
# NOTE: NSX_SEGGER_DEVICE is only used for J-Link flashing, not for the
# configure/build path. Confirm the exact J-Link device string before flashing.
set(NSX_SEGGER_DEVICE "AMA2B2KK-KBR")
set(NSX_SEGGER_IF_SPEED "4000")
set(NSX_SEGGER_PF_ADDR "0x0000")
set(NSX_SEGGER_CPUFREQ "48000000")
set(NSX_SEGGER_SWOFREQ "1000000")
