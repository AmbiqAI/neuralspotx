"""Public request-versus-keyword semantics for the dual-form facade."""

import warnings
from dataclasses import dataclass, replace
from pathlib import Path
from unittest.mock import patch

import pytest

import neuralspotx as nsx


def test_frozen_build_and_explicit_defaults(tmp_path: Path) -> None:
    request = nsx.AppBuildRequest(tmp_path, jobs=4, board="apollo510_evb", frozen=True)
    with patch("neuralspotx.operations.build_app_impl") as build:
        with pytest.raises(nsx.NSXConfigError, match="frozen"):
            nsx.build_app(nsx.AppBuildRequest(tmp_path), frozen=True)
        with pytest.raises(nsx.NSXConfigError, match="frozen"):
            nsx.build_app(request, frozen=False)
        with pytest.raises(nsx.NSXConfigError, match="jobs"):
            nsx.build_app(request, jobs=8)
        with pytest.raises(nsx.NSXConfigError, match="board"):
            nsx.build_app(app_dir=request, board=None)
        build.assert_not_called()
        lines: list[str] = []
        nsx.build_app(request, frozen=True, on_line=lines.append)
        assert build.call_args.kwargs["frozen"] is True
        assert build.call_args.kwargs["jobs"] == 4
        build.call_args.kwargs["on_line"]("compile")
        assert lines == ["compile"]
        nsx.build_app(replace(request, frozen=False, jobs=8))
        assert build.call_args.kwargs["frozen"] is False
        assert request.frozen and request.jobs == 4


def test_lock_check_has_no_write_fallback(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject: {name: demo}\ntarget: {board: apollo510_evb, soc: apollo510}\n"
        "baseline: none\nmodules: []\n",
        encoding="utf-8",
    )
    request = nsx.AppLockRequest(tmp_path)
    with pytest.raises(nsx.NSXConfigError, match="check"):
        nsx.lock_app(app_dir=request, check=True)
    assert list(tmp_path.iterdir()) == [tmp_path / "nsx.yml"]
    with pytest.raises(nsx.NSXError):
        nsx.lock_app(replace(request, check=True))
    assert not (tmp_path / "nsx.lock").exists()
    lock = nsx.lock_app(tmp_path)
    assert lock.path is not None
    before = lock.path.read_bytes()
    nsx.lock_app(replace(request, check=True), check=True)
    assert lock.path.read_bytes() == before


def test_positional_module_name_and_call_callbacks(tmp_path: Path) -> None:
    change = nsx.ModuleChangeRequest(tmp_path, "driver", dry_run=True)
    with patch("neuralspotx.operations.add_module_impl") as add:
        with pytest.raises(nsx.NSXConfigError, match="module conflicts"):
            nsx.add_module(change, "different")
        add.assert_not_called()
        nsx.add_module(change, "driver")
        add.assert_called_once()
    with patch("neuralspotx.operations.create_app_impl") as create:
        nsx.create_app(nsx.AppCreateRequest(tmp_path), emit=lambda event: None)
        create.assert_called_once()


def test_inapplicable_request_fields(tmp_path: Path) -> None:
    with patch("neuralspotx.operations.build_app_impl") as build:
        with pytest.warns(DeprecationWarning, match="probe_serial"):
            nsx.build_app(nsx.AppBuildRequest(tmp_path, probe_serial="1"))
        build.assert_called_once()
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with pytest.raises(nsx.NSXConfigError, match="frozen"):
            nsx.clean_app(nsx.AppCleanRequest(tmp_path, frozen=True, probe_serial="1"))
    with patch("neuralspotx.operations.remove_module_impl") as remove:
        with pytest.warns(DeprecationWarning, match="boards"):
            nsx.remove_module(nsx.ModuleChangeRequest(tmp_path, "one", boards=("test",)))
        remove.assert_called_once()
    with patch("neuralspotx.operations.configure_app_impl") as configure:
        with pytest.warns(DeprecationWarning, match="jobs"):
            nsx.configure_app(nsx.AppBuildRequest(tmp_path, jobs=4))
        configure.assert_called_once()
    assert not list(tmp_path.iterdir())


def test_user_request_subclass_can_carry_metadata(tmp_path: Path) -> None:
    @dataclass
    class AnnotatedBuild(nsx.AppBuildRequest):
        experiment: str = "baseline"

    with patch("neuralspotx.operations.build_app_impl") as build:
        nsx.build_app(AnnotatedBuild(tmp_path, experiment="qualification"))
        build.assert_called_once()


def test_init_module_keeps_documented_1x_precedence(tmp_path: Path) -> None:
    request = nsx.ModuleInitRequest(tmp_path, force=False)
    with patch("neuralspotx.operations.init_module_impl") as init:
        with pytest.warns(DeprecationWarning, match="force conflicts"):
            nsx.init_module(request, force=True)
        init.assert_called_once_with(request)
        assert request.force is False


def test_public_frozen_request_refuses_modified_input(tmp_path: Path) -> None:
    (tmp_path / "nsx.yml").write_text(
        "schema_version: 2\nproject: {name: demo}\ntarget: {board: apollo510_evb, soc: apollo510}\n"
        "baseline: none\nmodules: [{name: sensor, source: {vendored: true}}]\n",
        encoding="utf-8",
    )
    source = tmp_path / "modules/sensor/driver.c"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original")
    nsx.lock_app(tmp_path)
    source.write_bytes(b"edited")
    with pytest.raises(nsx.NSXError, match="sensor"):
        nsx.build_app(nsx.AppBuildRequest(tmp_path, frozen=True))
    assert source.read_bytes() == b"edited"
