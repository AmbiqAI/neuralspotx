"""Closure order honors optional dependencies that are present.

``NSX_APP_MODULES`` is emitted in closure order and CMake adds the modules in
that order, so a module that probes for an optional dependency's target (e.g.
``nsx-tflite-micro`` checking for ``nsx::arm_cmsis_nn``) must come after it.
Optional deps still never pull a module into the closure.
"""

from __future__ import annotations

import pytest

from neuralspotx.models import ModuleMetadata
from neuralspotx.module_registry import _closure


def _meta(name: str, required: list[str] | None = None, optional: list[str] | None = None) -> dict:
    return {
        "module": {"name": name, "type": "library", "version": "0.0.0"},
        "support": {"ambiqsuite": True, "zephyr": False},
        "depends": {"required": required or [], "optional": optional or []},
        "compatibility": {"boards": ["*"], "socs": ["*"], "toolchains": ["*"]},
    }


def _resolve(
    graph: dict[str, dict], seeds: list[str], monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    monkeypatch.delenv("NSX_SKIP_COMPAT_CHECK", raising=False)
    monkeypatch.setattr(
        _closure,
        "_load_module_metadata",
        lambda name, registry, app_dir=None: ModuleMetadata.from_raw(graph[name]),
    )
    return _closure._resolve_module_closure(
        seeds,
        app_dir=None,
        nsx_cfg={
            "target": {"board": "apollo510_evb", "soc": "apollo510"},
            "toolchain": "arm-none-eabi-gcc",
            "modules": [{"name": seed} for seed in seeds],
        },
        registry={},
        default_toolchain="arm-none-eabi-gcc",
    )


def test_present_optional_dep_precedes_dependent(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = {
        "src": _meta("src"),
        "tflm": _meta("tflm", required=["src"], optional=["cmsis"]),
        "cmsis": _meta("cmsis"),
    }
    order = _resolve(graph, ["tflm", "cmsis"], monkeypatch)
    assert sorted(order) == ["cmsis", "src", "tflm"]
    assert order.index("cmsis") < order.index("tflm")
    assert order.index("src") < order.index("tflm")


def test_absent_optional_dep_is_not_pulled_in(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = {"tflm": _meta("tflm", optional=["cmsis"])}
    assert _resolve(graph, ["tflm"], monkeypatch) == ["tflm"]


def test_order_without_optional_edges_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = {
        "a": _meta("a", required=["c"]),
        "b": _meta("b"),
        "c": _meta("c"),
    }
    assert _resolve(graph, ["a", "b"], monkeypatch) == ["c", "a", "b"]


def test_optional_edge_closing_a_cycle_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = {
        "a": _meta("a", required=["b"]),
        "b": _meta("b", optional=["a"]),
    }
    assert _resolve(graph, ["a"], monkeypatch) == ["b", "a"]
