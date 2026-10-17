"""Closure order honors optional dependencies that are present.

``NSX_APP_MODULES`` is emitted in closure order and CMake adds the modules in
that order, so a module that probes for an optional dependency's target (e.g.
``nsx-tflite-micro`` checking for ``nsx::arm_cmsis_nn``) must come after it.
Optional deps still never pull a module into the closure.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

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


def test_required_edge_wins_over_a_cycle_of_optional_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # y opt-> p opt-> q req-> y: accepting both optional edges would put q
    # before y, which q requires. Required edges must decide.
    graph = {
        "y": _meta("y", optional=["p"]),
        "p": _meta("p", optional=["q"]),
        "q": _meta("q", required=["y"]),
    }
    order = _resolve(graph, ["y", "p", "q"], monkeypatch)
    assert order.index("y") < order.index("q")


def test_optional_dep_brings_its_required_deps_with_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Moving o ahead of x must also move r, which o requires, ahead of o.
    graph = {
        "x": _meta("x", optional=["o"]),
        "o": _meta("o", required=["r"]),
        "r": _meta("r"),
    }
    order = _resolve(graph, ["x", "o"], monkeypatch)
    assert order.index("r") < order.index("o") < order.index("x")


@st.composite
def _graphs(draw: st.DrawFn) -> tuple[list[str], dict[str, ModuleMetadata]]:
    size = draw(st.integers(min_value=1, max_value=8))
    names = [f"m{i}" for i in range(size)]
    cache: dict[str, ModuleMetadata] = {}
    for i, name in enumerate(names):
        # Required deps only point at earlier modules, so the index order is a
        # valid required-only closure order, as the closure walk produces.
        required = draw(st.lists(st.sampled_from(names[:i]), unique=True)) if i else []
        optional = draw(st.lists(st.sampled_from(names), unique=True))
        cache[name] = ModuleMetadata.from_raw(_meta(name, required, optional))
    return names, cache


@given(_graphs())
@settings(max_examples=300, deadline=None)
def test_reordering_never_breaks_a_required_edge(
    graph: tuple[list[str], dict[str, ModuleMetadata]],
) -> None:
    resolved, cache = graph
    order = _closure._order_with_present_optional_deps(resolved, cache)
    assert sorted(order) == sorted(resolved)
    for name in resolved:
        for dep in cache[name].required_deps:
            assert order.index(dep) < order.index(name)
    if not any(cache[name].optional_deps for name in resolved):
        assert order == resolved
