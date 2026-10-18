"""Every example resolves the packaged registry's nsx-ambiq-sdk release.

An app-local ``module_registry`` override can pin a project to an older
revision than the packaged registry. For the SDK that leaves an example
mixing two SDK releases in one lock (the overridden modules on the old
release, the board and SoC modules on the packaged one), which no build or
lock check reports. The examples are the reference apps, so they track the
packaged pin.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_EXAMPLES = sorted(p.parent for p in (_REPO / "examples").glob("*/nsx.lock"))
_SDK_PROJECT = "nsx-ambiq-sdk"


def _registry_sdk_revision() -> str:
    registry = yaml.safe_load(
        (_REPO / "src" / "neuralspotx" / "data" / "registry.lock.yaml").read_text(encoding="utf-8")
    )
    return registry["projects"][_SDK_PROJECT]["revision"]


def test_examples_are_found() -> None:
    assert _EXAMPLES


@pytest.mark.parametrize("example", _EXAMPLES, ids=lambda p: p.name)
def test_example_does_not_override_the_sdk_project(example: Path) -> None:
    manifest = yaml.safe_load((example / "nsx.yml").read_text(encoding="utf-8"))
    overrides = (manifest.get("module_registry") or {}).get("projects") or {}
    assert _SDK_PROJECT not in overrides, (
        f"{example.name}/nsx.yml overrides {_SDK_PROJECT}; examples resolve the packaged registry's SDK release"
    )


@pytest.mark.parametrize("example", _EXAMPLES, ids=lambda p: p.name)
def test_example_lock_resolves_one_sdk_release(example: Path) -> None:
    expected = _registry_sdk_revision()
    lock = yaml.safe_load((example / "nsx.lock").read_text(encoding="utf-8"))
    found = {
        (target_name, module_name): entry["constraint"]
        for target_name, target in lock["targets"].items()
        for module_name, entry in target["modules"].items()
        if entry.get("project") == _SDK_PROJECT
    }
    assert found, f"{example.name}/nsx.lock resolves no {_SDK_PROJECT} module"
    wrong = {key: constraint for key, constraint in found.items() if constraint != expected}
    assert not wrong, (
        f"{example.name}/nsx.lock resolves {_SDK_PROJECT} modules away from {expected}: {wrong}"
    )
