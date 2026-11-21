"""Check the pilot's guest-to-host exit contract without an installed Arm FVP."""

import runpy
from pathlib import Path

import pytest

guest_result = runpy.run_path(
    str(Path(__file__).parent / "fixtures" / "corstone-pilot" / "run.py")
)["guest_result"]
PASS = (
    b"NSX pilot hello\r\nsuite.c:35:test_signed_dot_product:PASS\r\n\r\n"
    b"-----------------------\r\n1 Tests 0 Failures 0 Ignored \r\nOK\r\n"
)
EXIT_OK = b"Application exit code: 0.\r\n\x04"


@pytest.mark.parametrize("suffix", [b"", b"\r\nEXITTHESIM", b"\r\nEXITTHESIM\r\n"])
def test_pilot_accepts_both_arm_shutdown_mechanisms(suffix: bytes) -> None:
    assert guest_result(PASS + EXIT_OK + suffix) == 0


def test_pilot_propagates_guest_failure() -> None:
    assert guest_result(b"1 Tests 1 Failures 0 Ignored\nFAIL\nApplication exit code: 1.\n\x04") == 1


@pytest.mark.parametrize(
    "uart",
    [
        b"",
        PASS,
        EXIT_OK,
        PASS + EXIT_OK[:-1],
        PASS + EXIT_OK + b"garbage",
        EXIT_OK + PASS + EXIT_OK,
        PASS + PASS + EXIT_OK,
        PASS + b"OK\r\n" + EXIT_OK,
        b"1 Tests 1 Failures 0 Ignored\r\nFAIL\r\n" + PASS + EXIT_OK,
    ],
)
def test_pilot_rejects_incomplete_or_ambiguous_success(uart: bytes) -> None:
    assert guest_result(uart) == 2
