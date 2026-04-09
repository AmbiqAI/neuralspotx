# SEGGER configuration for Apollo330P / Apollo510L family.
#
# NSX_SEGGER_CPUFREQ is the TPIU *trace clock*, NOT the CPU clock.
# JLink SWO viewer uses this to calculate the SWO baud rate scaler (ACPR).
# On Apollo330P the trace clock is XTAL_HS = 48 MHz.
set(NSX_SEGGER_DEVICE "Apollo330P_510L")
set(NSX_SEGGER_IF_SPEED "4000")
set(NSX_SEGGER_PF_ADDR "0x00410000")
set(NSX_SEGGER_CPUFREQ "48000000")
set(NSX_SEGGER_SWOFREQ "1000000")
