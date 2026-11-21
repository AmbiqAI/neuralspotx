"""Run the Corstone-300 Unity pilot on Linux. Arguments: FVP executable, ELF."""

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path


def guest_result(uart: bytes) -> int:
    """The model can exit successfully when the firmware fails."""
    text = uart.replace(b"\r\n", b"\n")
    # Arm retarget ends at EOT on some models, at the subsequent shutdown tag on others.
    result = re.search(
        rb"^Application exit code: (0|[1-9][0-9]*)\.\n\x04(?:\nEXITTHESIM\n?)?\Z",
        text,
        re.MULTILINE,
    )
    if result is None or text.count(b"Application exit code:") != 1:
        return 2
    if result[1] != b"0":
        return 1
    # This fixture runs exactly one pinned suite. A restarted or truncated
    # transcript must never certify a pass merely because it contains "OK".
    success = re.fullmatch(
        rb"NSX pilot hello\n"
        rb"[^\n]+:[0-9]+:test_signed_dot_product:PASS\n\n-+\n"
        rb"1 Tests 0 Failures 0 Ignored *\nOK\n",
        text[: result.start()],
    )
    return 0 if success else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fvp", type=Path)
    parser.add_argument("elf", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        uart = Path(directory) / "uart.log"
        settings = [
            "cpu0.CFGDTCMSZ=12",
            "cpu0.CFGITCMSZ=12",
            "mps3_board.visualisation.disable-visualisation=1",
            *(f"mps3_board.telnetterminal{port}.start_telnet=0" for port in (0, 1, 2, 5)),
            f"mps3_board.uart0.out_file={uart}",
            "mps3_board.uart0.unbuffered_output=1",
            "mps3_board.uart0.shutdown_on_eot=1",
            "mps3_board.uart0.shutdown_tag=EXITTHESIM",
        ]
        command = [str(args.fvp.resolve())]
        for setting in settings:
            command.extend(["-C", setting])
        command.extend(["-a", str(args.elf.resolve())])
        try:
            process = subprocess.run(command, cwd=directory, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            print(error, file=sys.stderr)
            return 2
        finally:
            output = uart.read_bytes() if uart.exists() else b""
            sys.stdout.buffer.write(output)
        if process.returncode:
            print(f"FVP exited with status {process.returncode}", file=sys.stderr)
            return 2
        result = guest_result(output)
        if result == 2:
            print("Incomplete Unity or guest exit record", file=sys.stderr)
        return result


if __name__ == "__main__":
    raise SystemExit(main())
