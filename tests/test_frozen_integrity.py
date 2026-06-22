"""Phase 5 — sync --frozen content_hash verification (NSXIntegrityError)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXIntegrityError, NSXModuleError
from neuralspotx.operations import lock_app_impl, sync_app_impl


def _write_nsx_yml(app_dir: Path, modules: list[dict[str, Any]]) -> None:
    cfg = {
        "schema_version": 2,
        "project": {"name": "testapp"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "modules": modules,
    }
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _make_vendored(app_dir: Path, name: str, content: str = "hello") -> Path:
    mod = app_dir / "modules" / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "src.c").write_text(content, encoding="utf-8")
    return mod


class TestFrozenContentHashIntegrity:
    def test_mutated_module_raises_integrity_error_with_module_name(self, tmp_path: Path) -> None:
        """Vendor a module, mutate one file, run sync --frozen → NSXIntegrityError."""

        _make_vendored(tmp_path, "modA", content="original")
        _write_nsx_yml(tmp_path, [{"name": "modA", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)

        # Mutate the file mid-tree.
        (tmp_path / "modules" / "modA" / "src.c").write_text("MUTATED", encoding="utf-8")

        with pytest.raises(NSXIntegrityError) as excinfo:
            sync_app_impl(tmp_path, frozen=True)

        # Must name the offending module.
        assert "modA" in str(excinfo.value)
        assert excinfo.value.module == "modA"

    def test_integrity_error_is_module_error_subclass(self, tmp_path: Path) -> None:
        """``except NSXModuleError`` continues to catch integrity failures."""

        _make_vendored(tmp_path, "modB")
        _write_nsx_yml(tmp_path, [{"name": "modB", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)
        (tmp_path / "modules" / "modB" / "src.c").write_text("X", encoding="utf-8")

        with pytest.raises(NSXModuleError):
            sync_app_impl(tmp_path, frozen=True)

    def test_clean_tree_passes(self, tmp_path: Path) -> None:
        _make_vendored(tmp_path, "modC")
        _write_nsx_yml(tmp_path, [{"name": "modC", "source": {"vendored": True}}])
        lock_app_impl(tmp_path)

        sync_app_impl(tmp_path, frozen=True)  # must not raise
