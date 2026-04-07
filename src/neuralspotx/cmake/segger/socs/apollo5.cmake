# SEGGER configuration for Apollo510 / Apollo5 family.
#
# NSX_SEGGER_CPUFREQ is the TPIU *trace clock*, NOT the CPU clock.
# JLink SWO viewer uses this to calculate the SWO baud rate scaler (ACPR).
# On Apollo510 the trace clock is HFRC_96MHz. The HAL configures TPIU with
# this clock source, so we pass 96 MHz here regardless of the actual CPU
# frequency (which can be 96 MHz LP or 192 MHz HP).
set(NSX_SEGGER_DEVICE "AP510NFA-CBR")
set(NSX_SEGGER_IF_SPEED "4000")
set(NSX_SEGGER_PF_ADDR "0x00410000")
set(NSX_SEGGER_CPUFREQ "96000000")
set(NSX_SEGGER_SWOFREQ "1000000")
