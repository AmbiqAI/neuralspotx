"""Phase 3: ``nsx board`` CLI group (list / show / create)."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from neuralspotx import cli


def _invoke(*args: str) -> tuple[str, str, int]:
    out, err = io.StringIO(), io.StringIO()
    code = 0
    with redirect_stdout(out), redirect_stderr(err):
        try:
            code = cli.main(list(args)) or 0
        except SystemExit as exc:
            code = int(exc.code) if exc.code is not None else 0
    return out.getvalue(), err.getvalue(), code


def test_board_list_json_lists_known_boards() -> None:
    stdout, stderr, code = _invoke("board", "list", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    names = {b["name"] for b in payload}
    assert "apollo510_evb" in names
    for board in payload:
        assert set(board.keys()) >= {
            "name",
            "tier",
            "soc",
            "sdk_provider",
            "registered",
            "cpu",
            "toolchains",
        }


def test_board_list_registered_only_filters() -> None:
    stdout, _stderr, code = _invoke("board", "list", "--registered-only", "--json")
    assert code == 0
    payload = json.loads(stdout)
    assert payload, "expected at least one registered board"
    assert all(b["registered"] for b in payload)


def test_board_show_json() -> None:
    stdout, stderr, code = _invoke("board", "show", "apollo510_evb", "--json")
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["name"] == "apollo510_evb"
    assert payload["soc"] == "apollo510"


def test_board_show_unknown_raises() -> None:
    _stdout, stderr, code = _invoke("board", "show", "not_a_board", "--json")
    assert code != 0
    assert "unknown board" in stderr


def test_board_create_scaffolds_inheriting_board(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "project:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
        encoding="utf-8",
    )
    stdout, stderr, code = _invoke(
        "board",
        "create",
        "my510",
        "--from",
        "apollo510_evb",
        "--app-dir",
        str(tmp_path),
        "--json",
    )
    assert code == 0, stderr
    payload = json.loads(stdout)
    assert payload["name"] == "my510"
    assert payload["tier"] == "custom"
    assert payload["registered"] is False
    assert payload["soc"] == "apollo510"

    board_dir = tmp_path / "boards" / "my510"
    assert (board_dir / "board.yaml").is_file()
    assert (board_dir / "board.cmake").is_file()
    assert "inherits: apollo510_evb" in (board_dir / "board.yaml").read_text()


def test_board_create_unknown_parent_raises(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "project:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
        encoding="utf-8",
    )
    _stdout, stderr, code = _invoke(
        "board",
        "create",
        "x",
        "--from",
        "nope",
        "--app-dir",
        str(tmp_path),
    )
    assert code != 0
    assert "unknown parent board" in stderr


def test_board_create_existing_dir_requires_force(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "project:\n  name: demo\ntarget:\n  board: apollo510_evb\n",
        encoding="utf-8",
    )
    args = [
        "board",
        "create",
        "my510",
        "--from",
        "apollo510_evb",
        "--app-dir",
        str(tmp_path),
    ]
    _out1, _err1, code1 = _invoke(*args)
    assert code1 == 0
    _out2, err2, code2 = _invoke(*args)
    assert code2 != 0
    assert "already exists" in err2
    # --force overwrites cleanly.
    _out3, _err3, code3 = _invoke(*args, "--force")
    assert code3 == 0
