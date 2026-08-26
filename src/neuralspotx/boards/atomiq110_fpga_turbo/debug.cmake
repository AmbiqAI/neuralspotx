# Role fragment: debug. Debug-probe / SEGGER device facts.
set(NSX_SEGGER_DEVICE "Atomiq110")

# SWO viewer clocking (overrides the atomiq110 SoC facts, which assume a
# 25 MHz trace clock). On the FPGA "turbo" board the TPIU trace clock is
# left at its hardware reset default (firmware cannot touch CRM_TPIUCLKCFG,
# see nsx-core src/atomiq110/nsx_system_platform.c), and that default
# measures 48 MHz, not 25 MHz. The firmware programs ACPR for a 25 MHz
# clock (prescaler 25), so the real SWO baud is 48 MHz / 25 = 1.92 MHz.
# Tell the viewer the true trace clock and the true baud so its ACPR
# override (48 MHz / 1.92 MHz - 1 = 24) matches what the firmware set and
# the decoder runs at the actual line rate. Verified on hardware
# (J-Link Compact PLUS, 2026-08): 25 MHz/1 MHz decodes as gibberish,
# 48 MHz/1.92 MHz decodes cleanly.
set(NSX_SEGGER_CPUFREQ "48000000")
set(NSX_SEGGER_SWOFREQ "1920000")
