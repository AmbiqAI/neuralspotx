#!/usr/bin/env python3
"""
Joulescope power capture helper for NSX CoreMark (and similar GPIO-gated benchmarks).

Protocol (2-bit GPIO via ns_set_power_monitor_state):
  State 0 (GPI=0b00): IDLE / sleep
  State 1 (GPI=0b01): ACTIVE compute
  State 3 (GPI=0b11): SIGNAL (start/stop marker)

The script watches GPI transitions and accumulates per-phase statistics.

Usage:
    python joulescope_capture.py              # continuous capture until Ctrl-C
    python joulescope_capture.py --duration 120  # capture for 120 seconds

Requires:  pip install joulescope
"""

import argparse
import queue
import signal
import sys
import time

try:
    from joulescope import scan
except ImportError:
    print("Install joulescope: pip install joulescope")
    sys.exit(1)


# ── Accumulation state ──────────────────────────────────────

class PhaseStats:
    """Accumulate Joulescope statistics for a named phase."""

    def __init__(self, name: str):
        self.name = name
        self.samples = 0
        self.current_sum = 0.0   # amps
        self.voltage_sum = 0.0   # volts
        self.power_sum = 0.0     # watts
        self.charge = 0.0        # coulombs
        self.energy = 0.0        # joules
        self.start_time = None
        self.total_seconds = 0.0

    def start(self):
        self.start_time = time.monotonic()

    def stop(self):
        if self.start_time is not None:
            self.total_seconds += time.monotonic() - self.start_time
            self.start_time = None

    def accumulate(self, stats):
        self.samples += 1
        self.current_sum += stats["signals"]["current"]["µ"]["value"]
        self.voltage_sum += stats["signals"]["voltage"]["µ"]["value"]
        self.power_sum += stats["signals"]["power"]["µ"]["value"]
        self.charge = stats["accumulators"]["charge"]["value"]
        self.energy = stats["accumulators"]["energy"]["value"]

    @property
    def avg_current_ma(self):
        return (self.current_sum / self.samples * 1000) if self.samples else 0

    @property
    def avg_voltage(self):
        return (self.voltage_sum / self.samples) if self.samples else 0

    @property
    def avg_power_mw(self):
        return (self.power_sum / self.samples * 1000) if self.samples else 0

    def summary(self):
        return (
            f"  {self.name:12s}: "
            f"I={self.avg_current_ma:8.3f} mA  "
            f"V={self.avg_voltage:6.3f} V  "
            f"P={self.avg_power_mw:8.3f} mW  "
            f"t={self.total_seconds:7.1f} s  "
            f"samples={self.samples}"
        )


active_stats = PhaseStats("ACTIVE")
sleep_stats = PhaseStats("SLEEP")
current_phase = None        # "active", "sleep", or None
last_gpi = None


# ── Joulescope callbacks ────────────────────────────────────

stats_queue = queue.Queue()


def stats_callback_factory(device):
    def cbk(data, indicator=None):
        stats_queue.put(data)
    return cbk


def process_stats(data):
    global current_phase
    if current_phase == "active":
        active_stats.accumulate(data)
    elif current_phase == "sleep":
        sleep_stats.accumulate(data)


def process_gpi(device):
    """Read Joulescope GPI and detect phase transitions."""
    global current_phase, last_gpi

    gpi = device.extio_status()["gpi_value"]["value"]
    if gpi == last_gpi:
        return
    last_gpi = gpi

    # GPI bit0 = GPIO_0, bit1 = GPIO_1
    if gpi & 0x01:  # bit 0 high = ACTIVE
        if current_phase != "active":
            if current_phase == "sleep":
                sleep_stats.stop()
            current_phase = "active"
            active_stats.start()
            print(f"[{time.strftime('%H:%M:%S')}] -> ACTIVE (compute)")
    elif gpi == 0:  # both low = SLEEP / IDLE
        if current_phase != "sleep":
            if current_phase == "active":
                active_stats.stop()
            current_phase = "sleep"
            sleep_stats.start()
            print(f"[{time.strftime('%H:%M:%S')}] -> SLEEP")
    # gpi == 3 is the "signal" marker; we ignore it for now


def drain_queue():
    while True:
        try:
            data = stats_queue.get(block=False)
            process_stats(data)
        except queue.Empty:
            return


# ── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Joulescope capture for NSX benchmarks")
    parser.add_argument("--duration", type=float, default=0,
                        help="Capture duration in seconds (0 = until Ctrl-C)")
    parser.add_argument("--io-voltage", default="1.8V", choices=["1.8V", "3.3V"],
                        help="Joulescope GPIO voltage level (default: 1.8V)")
    parser.add_argument("--reduction-freq", default="50 Hz",
                        help="Statistics reduction frequency (default: 50 Hz)")
    args = parser.parse_args()

    quit_flag = False
    def on_sigint(*_):
        nonlocal quit_flag
        quit_flag = True
    signal.signal(signal.SIGINT, on_sigint)

    devices = scan(config="auto")
    if not devices:
        print("ERROR: No Joulescope found. Is it connected?")
        return 1

    device = devices[0]
    cbk = stats_callback_factory(device)
    device.statistics_callback_register(cbk, "sensor")
    device.close()

    try:
        device.open()
    except Exception as exc:
        print(f"ERROR: Cannot open Joulescope (close the Joulescope app first): {exc}")
        return 1

    device.parameter_set("sensor_power", "on")
    device.parameter_set("i_range", "auto")
    device.parameter_set("v_range", "15V")
    device.parameter_set("io_voltage", args.io_voltage)
    device.parameter_set("reduction_frequency", args.reduction_freq)
    device.statistics_accumulators_clear()

    print(f"Joulescope ready — GPIO voltage {args.io_voltage}, waiting for phase transitions...")
    print("Press Ctrl-C to stop and print summary.\n")

    start = time.monotonic()
    try:
        while not quit_flag:
            if args.duration and (time.monotonic() - start) > args.duration:
                break
            process_gpi(device)
            device.status()
            time.sleep(0.02)
            drain_queue()
    finally:
        # Stop any running phase
        if current_phase == "active":
            active_stats.stop()
        elif current_phase == "sleep":
            sleep_stats.stop()

        try:
            device.stop()
            device.close()
        except Exception:
            pass  # swallow teardown errors — USB can timeout

    # ── Summary ──────────────────────────────────────────────
    print("\n" + "=" * 72)
    print("CAPTURE SUMMARY")
    print("=" * 72)
    print(active_stats.summary())
    print(sleep_stats.summary())

    if active_stats.avg_power_mw > 0:
        print(f"\n  CoreMark/mW = CoreMark_score / {active_stats.avg_power_mw:.3f} mW")
        print("  (plug in your CoreMark score from SWO output)")

    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
