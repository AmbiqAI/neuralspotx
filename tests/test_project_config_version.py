from __future__ import annotations

from pathlib import Path

from neuralspotx import project_config


def test_nsx_tool_version_prefers_source_checkout_version(tmp_path: Path, monkeypatch) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "neuralspotx"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    fake_module = tmp_path / "src" / "neuralspotx" / "project_config.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(project_config, "__file__", str(fake_module))
    monkeypatch.setattr(project_config, "package_version", lambda _name: "0.5.1")

    assert project_config._nsx_tool_version() == "9.9.9"


def test_nsx_tool_version_falls_back_to_installed_metadata(tmp_path: Path, monkeypatch) -> None:
    fake_module = tmp_path / "src" / "neuralspotx" / "project_config.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(project_config, "__file__", str(fake_module))
    monkeypatch.setattr(project_config, "package_version", lambda _name: "1.2.3")

    assert project_config._nsx_tool_version() == "1.2.3"
