"""Exercise native adapter sequencing with a fake SDK, never a physical probe."""

from __future__ import annotations

import argparse
import sys
from types import ModuleType, SimpleNamespace

import pytest

from neuralspotx import _rtt_worker as worker
from neuralspotx.tooling import JLinkProbe


@pytest.mark.parametrize("count", [0, 2])
def test_ambiguous_selection_rejected(monkeypatch: pytest.MonkeyPatch, count: int) -> None:
    monkeypatch.setattr(
        worker, "list_jlink_probes", lambda: [JLinkProbe(0, "1234", "fake")] * count
    )
    with pytest.raises(RuntimeError, match="probe-serial"):
        worker._select_serial(None)


def test_explicit_serial_skips_enumeration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "list_jlink_probes", lambda: pytest.fail("enumerated"))
    assert worker._select_serial("5678") == "5678"


@pytest.mark.parametrize("failure", [None, "open", "read", "stop"])
def test_native_order_readiness_and_cleanup(
    monkeypatch: pytest.MonkeyPatch, failure: str | None
) -> None:
    calls: list[str] = []
    events: list[tuple[str, str]] = []

    class FakeLink:
        polls = 0
        descriptors = 0

        def open(self, *, serial_no: int) -> None:
            assert serial_no == 1234
            calls.append("open")
            if failure == "open":
                raise RuntimeError("open failed")

        def set_tif(self, interface: int) -> None:
            assert interface == 1
            calls.append("interface")

        def connect(self, device: str, *, speed: int) -> None:
            assert device == "TestDevice" and speed == 4000
            calls.append("connect")

        def rtt_start(self, *, block_address: int) -> None:
            assert block_address == 0x20001000
            calls.append("start")

        def rtt_get_num_up_buffers(self) -> int:
            self.polls += 1
            if self.polls == 1:
                raise LookupError("not discovered")
            return 1

        def rtt_get_buf_descriptor(self, index: int, up: bool) -> SimpleNamespace:
            assert index == 0 and up
            self.descriptors += 1
            return SimpleNamespace(SizeOfBuffer=0 if self.descriptors == 1 else 128)

        def rtt_read(self, index: int, length: int) -> list[int]:
            assert index == 0 and length == 4096
            assert self.polls >= 3 and self.descriptors >= 2
            calls.append("read")
            if failure == "read":
                raise RuntimeError("read failed")
            return [0, 255]

        def rtt_stop(self) -> None:
            calls.append("stop")
            if failure == "stop":
                raise RuntimeError("stop failed")

        def close(self) -> None:
            calls.append("close")

    fake = ModuleType("pylink")
    setattr(fake, "JLink", FakeLink)
    setattr(fake, "enums", SimpleNamespace(JLinkInterfaces=SimpleNamespace(SWD=1)))
    setattr(fake, "errors", SimpleNamespace(JLinkRTTException=LookupError))
    monkeypatch.setitem(sys.modules, "pylink", fake)
    # Finite worker loop with time advancing independently of data availability.
    clock = iter([0, 0.01, 1])
    monkeypatch.setattr(worker.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)
    args = argparse.Namespace(
        serial="1234", device="TestDevice", speed=4000, address=0x20001000, duration=0.1
    )
    if failure:
        with pytest.raises(RuntimeError, match=f"{failure} failed"):
            worker._capture(args, lambda kind, payload: events.append((kind, payload)))
    else:
        worker._capture(args, lambda kind, payload: events.append((kind, payload)))
        assert events == [("ready", "1234"), ("data", "AP8=")]
        assert calls == ["open", "interface", "connect", "start", "read", "stop", "close"]
    assert calls[-1] == "close"
    assert ("stop" in calls) == (failure != "open")
