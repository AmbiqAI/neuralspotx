#!/usr/bin/env python3
"""
compare_regdump.py — Parse and compare register dumps from NSX and SDK5 builds.

Usage:
  # Compare two NSX-format captures:
  python compare_regdump.py nsx_dump.txt sdk5_dump.txt

  # Parse SDK5 PP JSON (snapshot 2) and compare against NSX dump:
  python compare_regdump.py --sdk5-json sdk5_uart.log nsx_dump.txt

  # Show only registers that differ:
  python compare_regdump.py --diff-only nsx_dump.txt sdk5_dump.txt

Input formats:
  NSX: "PWRCTRL.REGNAME = 0xHEXVAL"  (from dump_power_registers)
  SDK5 PP JSON: {"PWRCTRL": {"REGNAME": decimal, ...}}  (snapshot 2)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Map PP JSON key names to our register dump names.
# PP JSON uses flat names; we prefix with the peripheral block.
PP_BLOCKS = {
    "PWRCTRL": [
        "MCUPERFREQ",
        "DEVPWREN",
        "DEVPWRSTATUS",
        "AUDSSPWREN",
        "AUDSSPWRSTATUS",
        "MEMPWREN",
        "MEMPWRSTATUS",
        "MEMRETCFG",
        "SYSPWRSTATUS",
        "SSRAMPWREN",
        "SSRAMPWRST",
        "SSRAMRETCFG",
        "DEVPWREVENTEN",
        "MEMPWREVENTEN",
        "MMSOVERRIDE",
        "CPUPWRCTRL",
        "PWRCTRLMODESTATUS",
        "CPUPWRSTATUS",
        "PWRACKOVR",
        "PWRCNTDEFVAL",
        "GFXPERFREQ",
        "GFXPWRSWSEL",
        "EPURETCFG",
        "VRCTRL",
        "LEGACYVRLPOVR",
        "VRSTATUS",
        "SRAMCTRL",
        "ADCSTATUS",
        "AUDADCSTATUS",
        "TONCNTRCTRL",
        "LPOVRTHRESHVDDS",
        "LPOVRHYSTCNT",
        "LPOVRTHRESHVDDF",
        "LPOVRTHRESHVDDC",
        "LPOVRTHRESHVDDCLV",
        "LPOVRSTAT",
        "MRAMEXTCTRL",
        "EMONCTRL",
    ],
    "MCUCTRL": [
        "SIMOBUCK0",
        "SIMOBUCK1",
        "SIMOBUCK2",
        "SIMOBUCK3",
        "SIMOBUCK4",
        "SIMOBUCK5",
        "SIMOBUCK6",
        "SIMOBUCK7",
        "SIMOBUCK8",
        "SIMOBUCK9",
        "SIMOBUCK10",
        "SIMOBUCK11",
        "SIMOBUCK12",
        "SIMOBUCK13",
        "SIMOBUCK14",
        "SIMOBUCK15",
        "LDOREG1",
        "LDOREG2",
        "VRCTRL",
        "VREFGEN2",
        "VREFGEN4",
        "VREFBUF",
        "ACRG",
        "BGTLPCTRL",
        "MRAMCRYPTOPWRCTRL",
        "BODISABLE",
        "BODCTRL",
        "DBGCTRL",
        "PWRSW0",
        "PWRSW1",
        "PWRSW2",
        "ADCPWRCTRL",
        "AUDADCPWRCTRL",
        "PDMCTRL",
        "MMSMISCCTRL",
        "CPUCFG",
    ],
    "CLKGEN": [
        "CLKCTRL",
        "OCTRL",
        "CLKOUT",
        "CLOCKENSTAT",
        "CLOCKEN2STAT",
        "CLOCKEN3STAT",
        "LFRCCTRL",
        "MISC",
        "HFADJ",
        "HF2ADJ0",
        "HF2ADJ1",
        "HF2ADJ2",
        "DISPCLKCTRL",
    ],
}

# Registers most likely to affect power (highlight in diff)
POWER_CRITICAL = {
    "PWRCTRL.MCUPERFREQ",
    "PWRCTRL.DEVPWREN",
    "PWRCTRL.DEVPWRSTATUS",
    "PWRCTRL.MEMPWREN",
    "PWRCTRL.MEMPWRSTATUS",
    "PWRCTRL.MEMRETCFG",
    "PWRCTRL.SSRAMPWREN",
    "PWRCTRL.SSRAMPWRST",
    "PWRCTRL.SSRAMRETCFG",
    "PWRCTRL.VRCTRL",
    "PWRCTRL.VRSTATUS",
    "PWRCTRL.TONCNTRCTRL",
    "PWRCTRL.LPOVRTHRESHVDDS",
    "PWRCTRL.LPOVRTHRESHVDDF",
    "PWRCTRL.LPOVRTHRESHVDDC",
    "PWRCTRL.LPOVRTHRESHVDDCLV",
    "PWRCTRL.MRAMEXTCTRL",
    "MCUCTRL.SIMOBUCK0",
    "MCUCTRL.SIMOBUCK1",
    "MCUCTRL.SIMOBUCK2",
    "MCUCTRL.SIMOBUCK3",
    "MCUCTRL.SIMOBUCK4",
    "MCUCTRL.SIMOBUCK5",
    "MCUCTRL.SIMOBUCK6",
    "MCUCTRL.SIMOBUCK7",
    "MCUCTRL.SIMOBUCK8",
    "MCUCTRL.SIMOBUCK9",
    "MCUCTRL.SIMOBUCK10",
    "MCUCTRL.SIMOBUCK11",
    "MCUCTRL.SIMOBUCK12",
    "MCUCTRL.SIMOBUCK13",
    "MCUCTRL.SIMOBUCK14",
    "MCUCTRL.SIMOBUCK15",
    "MCUCTRL.LDOREG1",
    "MCUCTRL.LDOREG2",
    "MCUCTRL.VRCTRL",
    "MCUCTRL.VREFGEN2",
    "MCUCTRL.VREFGEN4",
    "MCUCTRL.MRAMCRYPTOPWRCTRL",
    "MCUCTRL.DBGCTRL",
    "MCUCTRL.BGTLPCTRL",
    "CLKGEN.CLKCTRL",
    "CLKGEN.CLOCKENSTAT",
}


def parse_nsx_dump(text: str) -> dict[str, int]:
    """Parse NSX register dump format: PERIPH.REG = 0xVALUE"""
    regs = {}
    for line in text.splitlines():
        m = re.match(r"\s*(\w+\.\w+)\s*=\s*0x([0-9A-Fa-f]+)", line)
        if m:
            regs[m.group(1)] = int(m.group(2), 16)
    return regs


def parse_pp_json(text: str, snapshot: int = 2) -> dict[str, int]:
    """Parse SDK5 PP JSON output for a given snapshot number.

    The PP tool outputs multiple JSON objects separated by newlines.
    Each object is for a peripheral block (PWRCTRL, MCUCTRL, CLKGEN, etc.)
    and contains a "SnapN" field indicating the snapshot number.
    """
    regs = {}
    # The PP JSON is not valid JSON — it's multiple separate JSON objects
    # printed with am_util_stdio_printf, potentially with trailing commas.
    # Try to extract JSON objects from the raw UART log.
    json_pattern = re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL)

    for match in json_pattern.finditer(text):
        blob = match.group()
        # Fix trailing commas before closing braces (common in PP output)
        blob = re.sub(r",\s*}", "}", blob)
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue

        # Find the peripheral block name and snapshot number
        for block_name, inner in obj.items():
            if not isinstance(inner, dict):
                continue
            snap_n = inner.get("SnapN", -1)
            if snap_n != snapshot:
                continue

            # Map register names to our PERIPH.REG format
            for reg_name, value in inner.items():
                if reg_name in ("Singleshot", "SnapN"):
                    continue
                if isinstance(value, int):
                    key = f"{block_name}.{reg_name}"
                    regs[key] = value

    return regs


def compare(
    a: dict[str, int], b: dict[str, int], label_a: str, label_b: str, diff_only: bool = False
) -> None:
    """Print side-by-side register comparison."""
    all_keys = sorted(set(a.keys()) | set(b.keys()))

    hdr = f"{'Register':<32s} {label_a:>12s}   {label_b:>12s}   {'Delta':>12s}  Note"
    print(hdr)
    print("-" * len(hdr))

    n_diff = 0
    for key in all_keys:
        va = a.get(key)
        vb = b.get(key)
        same = va == vb

        if diff_only and same:
            continue

        sa = f"0x{va:08X}" if va is not None else "     N/A    "
        sb = f"0x{vb:08X}" if vb is not None else "     N/A    "

        if va is not None and vb is not None and va != vb:
            delta = f"0x{(va ^ vb):08X}"
            n_diff += 1
        else:
            delta = "            "

        note = ""
        if key in POWER_CRITICAL and not same:
            note = " *** POWER-CRITICAL ***"

        marker = "  " if same else ">>"
        print(f"{marker} {key:<30s} {sa}   {sb}   {delta} {note}")

    print(f"\n{n_diff} register(s) differ out of {len(all_keys)} compared.")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("file_a", help="First register dump file (NSX format)")
    parser.add_argument("file_b", nargs="?", help="Second register dump file (NSX or PP JSON)")
    parser.add_argument(
        "--sdk5-json", action="store_true", help="Treat file_b as SDK5 PP JSON output"
    )
    parser.add_argument(
        "--snapshot", type=int, default=2, help="PP JSON snapshot number to use (default: 2)"
    )
    parser.add_argument("--diff-only", action="store_true", help="Show only registers that differ")
    parser.add_argument("--label-a", default="NSX", help="Label for file A")
    parser.add_argument("--label-b", default="SDK5", help="Label for file B")
    args = parser.parse_args()

    text_a = Path(args.file_a).read_text()
    regs_a = parse_nsx_dump(text_a)

    if args.file_b:
        text_b = Path(args.file_b).read_text()
        if args.sdk5_json:
            regs_b = parse_pp_json(text_b, args.snapshot)
        else:
            regs_b = parse_nsx_dump(text_b)

        if not regs_a:
            print(f"ERROR: No registers found in {args.file_a}", file=sys.stderr)
            sys.exit(1)
        if not regs_b:
            print(f"ERROR: No registers found in {args.file_b}", file=sys.stderr)
            sys.exit(1)

        compare(regs_a, regs_b, args.label_a, args.label_b, args.diff_only)
    else:
        # Single file — just print parsed registers
        if not regs_a:
            print(f"ERROR: No registers found in {args.file_a}", file=sys.stderr)
            sys.exit(1)
        print(f"{'Register':<32s} {'Value':>12s}  Note")
        print("-" * 60)
        for key in sorted(regs_a):
            note = " *** POWER-CRITICAL ***" if key in POWER_CRITICAL else ""
            print(f"  {key:<30s} 0x{regs_a[key]:08X} {note}")
        print(f"\n{len(regs_a)} registers parsed.")


if __name__ == "__main__":
    main()
