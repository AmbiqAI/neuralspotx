"""Phase 4: --json output for nsx doctor / cache info / commands / module list."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout

from neuralspotx import cli
from neuralspotx._errors import NSXToolchainError


def _invoke(*args: str) -> tuple[str, str, int]:
    """Run the CLI in-process and capture stdout/stderr/exit code."""
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(args))
        except SystemExit as exc:
            code = int(exc.code) if exc.code is not None else 0
        except NSXToolchainError as exc:
            err.write(str(exc))
            code = 1
    return out.getvalue(), err.getvalue(), code


def test_doctor_json_is_parsable_and_matches_dataclass_schema() -> None:
    stdout, _stderr, _code = _invoke("doctor", "--json")
    payload = json.loads(stdout)
    assert set(payload.keys()) >= {"ok", "checks", "notes"}
    assert isinstance(payload["ok"], bool)
    assert isinstance(payload["checks"], list)
    for check in payload["checks"]:
        assert set(check.keys()) >= {"label", "ok", "required", "detail", "hint"}


def test_cache_info_json_is_parsable() -> None:
    stdout, stderr, code = _invoke("cache", "info", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert set(payload.keys()) >= {
        "root",
        "disabled",
        "entry_count",
        "entries",
        "total_size_bytes",
    }
    assert isinstance(payload["entries"], list)


def test_commands_json_is_parsable() -> None:
    stdout, stderr, code = _invoke("commands", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert "commands" in payload
    assert isinstance(payload["commands"], list)


def test_probes_json_is_parsable(monkeypatch) -> None:
    monkeypatch.setattr(
        cli,
        "list_jlink_probes",
        lambda: [cli.JLinkProbe(index=0, serial="1160002204", product="J-Link-OB-Apollo4-CortexM")],
    )

    stdout, stderr, code = _invoke("probes", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload == [
        {
            "index": 0,
            "serial": "1160002204",
            "product": "J-Link-OB-Apollo4-CortexM",
            "nickname": None,
        }
    ]


def test_module_list_json_is_parsable() -> None:
    stdout, stderr, code = _invoke("module", "list", "--registry-only", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    # The CLI returns either a bare list (legacy) or a wrapper dict with a
    # ``modules`` array (registry-only scope). Accept both shapes.
    if isinstance(payload, dict):
        assert "modules" in payload
        assert isinstance(payload["modules"], list)
    else:
        assert isinstance(payload, list)


def test_probe_discovery_failure_is_not_empty_json(monkeypatch) -> None:
    import subprocess

    from neuralspotx import tooling

    monkeypatch.setattr(tooling, "find_segger_tool", lambda _: "/fake/JLinkExe")

    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("JLinkExe", 15)

    monkeypatch.setattr(tooling.subprocess, "run", fail)
    for args in [("probes",), ("probes", "--json")]:
        stdout, stderr, code = _invoke(*args)
        assert code != 0
        assert "timed out" in stderr
        assert not stdout
        assert "Traceback" not in stderr
