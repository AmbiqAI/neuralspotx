"""Regression tests for the M2 remediation item: ``shutil.rmtree`` callback
compatibility across Python 3.10/3.11 (``onerror=``) and 3.12+ (``onexc=``).

Python 3.12 deprecated ``onerror=`` in favour of ``onexc=`` and 3.14 will
remove it.  The ``_rmtree`` helpers in ``module_registry``, ``module_cache``
and ``subprocess_utils`` must:

* clean up trees containing read-only files (the original Windows-pack-file
  motivation),
* not emit a ``DeprecationWarning`` on Python 3.12+,
* still work on Python 3.10/3.11 where ``onexc=`` does not exist.
"""

from __future__ import annotations

import os
import stat
import sys
import warnings
from pathlib import Path

import pytest

from neuralspotx import module_cache, module_registry


def _make_readonly_tree(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    nested = root / "sub"
    nested.mkdir()
    f = nested / "ro.txt"
    f.write_text("read-only", encoding="utf-8")
    # Strip the write bit so a naive ``shutil.rmtree`` would fail on Windows
    # and (depending on parent perms) potentially elsewhere.
    os.chmod(f, stat.S_IREAD)


@pytest.mark.parametrize(
    "rmtree",
    [module_registry._rmtree, module_cache._rmtree],
    ids=["module_registry._rmtree", "module_cache._rmtree"],
)
def test_rmtree_clears_readonly_files(tmp_path: Path, rmtree) -> None:
    target = tmp_path / "tree"
    _make_readonly_tree(target)
    rmtree(target)
    assert not target.exists()


@pytest.mark.parametrize(
    "rmtree",
    [module_registry._rmtree, module_cache._rmtree],
    ids=["module_registry._rmtree", "module_cache._rmtree"],
)
def test_rmtree_is_noop_on_missing_path(tmp_path: Path, rmtree) -> None:
    rmtree(tmp_path / "does-not-exist")  # must not raise


@pytest.mark.parametrize(
    "rmtree",
    [module_registry._rmtree, module_cache._rmtree],
    ids=["module_registry._rmtree", "module_cache._rmtree"],
)
def test_rmtree_does_not_emit_deprecation_warning(tmp_path: Path, rmtree) -> None:
    target = tmp_path / "tree"
    _make_readonly_tree(target)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        rmtree(target)
    assert not target.exists()


@pytest.mark.parametrize(
    "module",
    [module_registry, module_cache],
    ids=["module_registry", "module_cache"],
)
def test_on_rm_error_retries_func_for_rmdir(tmp_path: Path, module) -> None:
    """Regression for #76: ``_on_rm_error`` must retry the original
    failing ``_func`` (e.g. ``os.rmdir``) rather than always calling
    ``os.unlink`` (which raises ``IsADirectoryError`` on directories).
    """
    import inspect

    # module_cache exposes _on_rm_error at module scope; module_registry
    # defines it inside _rmtree, so we extract it from the source and
    # assert structurally that the body retries _func(_path).
    src = inspect.getsource(module._rmtree if module is module_registry else module._on_rm_error)
    assert "os.unlink(_path)" not in src, (
        f"{module.__name__}._on_rm_error still calls os.unlink unconditionally; "
        "should retry _func(_path) so it works for os.rmdir too."
    )
    assert "_func(_path)" in src, (
        f"{module.__name__}._on_rm_error must retry _func(_path) — see issue #76."
    )

    # And exercise it directly: build a directory and feed (os.rmdir,
    # path) into the callback. With the old os.unlink-only body this
    # would silently leave the directory; with the fix it removes it.
    target = tmp_path / "rmdir_target"
    target.mkdir()

    if module is module_registry:
        # Inline callback — re-derive it through a dummy rmtree that
        # captures the kwarg.
        captured: dict[str, object] = {}
        import shutil as _shutil

        real_rmtree = _shutil.rmtree

        def _capture(path, **kwargs):  # type: ignore[no-untyped-def]
            captured["cb"] = kwargs.get("onexc") or kwargs.get("onerror")
            real_rmtree(path)

        import unittest.mock as _mock

        with _mock.patch.object(_shutil, "rmtree", _capture):
            spy_dir = tmp_path / "spy"
            spy_dir.mkdir()
            module._rmtree(spy_dir)
        cb = captured["cb"]
    else:
        cb = module._on_rm_error

    assert cb is not None
    cb(os.rmdir, str(target), None)
    assert not target.exists()


def test_uses_onexc_kwarg_on_py312_plus() -> None:
    """Drift guard: source must reference the version-correct kwarg."""
    src_root = Path(module_registry.__file__).resolve().parent.parent
    sources = (src_root / "module_cache.py").read_text(encoding="utf-8")
    # module_registry and subprocess_utils are packages as of phase 6 —
    # concatenate all submodule sources so the drift check still covers
    # the rmtree call sites wherever they live.
    for sub in sorted((src_root / "module_registry").glob("*.py")):
        sources += sub.read_text(encoding="utf-8")
    for sub in sorted((src_root / "subprocess_utils").glob("*.py")):
        sources += sub.read_text(encoding="utf-8")

    # Both branches of the version gate must be present in source.
    assert "onexc=_on_rm_error" in sources
    assert "onerror=_on_rm_error" in sources

    # On 3.12+, the runtime kwarg actually used must be onexc=. We assert
    # this indirectly: warnings filter above would catch onerror= use.
    if sys.version_info >= (3, 12):
        # rmtree with onerror= raises DeprecationWarning on 3.12+
        # — already covered by test_rmtree_does_not_emit_deprecation_warning.
        pass
