# SEGGER configuration for Apollo3P family.
#
# NSX_SEGGER_CPUFREQ is the TPIU *trace clock*, NOT the CPU clock.
# On Apollo3P the trace clock is 48 MHz (HFRC).
set(NSX_SEGGER_DEVICE "AMA3B2KK-KCR")
set(NSX_SEGGER_IF_SPEED "4000")
set(NSX_SEGGER_PF_ADDR "0xC000")
set(NSX_SEGGER_CPUFREQ "48000000")
set(NSX_SEGGER_SWOFREQ "1000000")
