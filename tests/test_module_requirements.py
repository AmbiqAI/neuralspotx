"""Dependency constraints exercised through authored YAML and shared workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx._errors import NSXModuleError
from neuralspotx.metadata import validate_nsx_module_metadata
from neuralspotx.models import ModuleMetadata
from neuralspotx.module_registry._closure import _resolve_module_closure
from neuralspotx.module_registry._discovery import _module_discovery_record
from neuralspotx.module_registry._requirements import validate_materialized_requirements


def manifest(
    name: str, version: object = "1.0", required: list[object] | None = None
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module": {"name": name, "type": "runtime", "version": version},
        "support": {"ambiqsuite": True, "zephyr": False},
        "build": {"cmake": {"package": name, "targets": [f"nsx::{name}"]}},
        "depends": {"required": required or [], "optional": []},
        "compatibility": {"boards": ["*"], "socs": ["*"], "toolchains": ["*"]},
    }


def project(
    tmp_path: Path, manifests: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry: dict[str, Any] = {"projects": {}, "modules": {}}
    for data in manifests:
        name = data["module"]["name"]
        source = tmp_path / "sources" / name
        source.mkdir(parents=True, exist_ok=True)
        (source / "nsx-module.yaml").write_text(yaml.safe_dump(data))
        # Core fixtures provide separate, initially matching source and build copies.
        mirror = tmp_path / "modules" / name
        mirror.mkdir(parents=True, exist_ok=True)
        (mirror / "nsx-module.yaml").write_text(yaml.safe_dump(data))
        registry["projects"][name] = {
            "local_path": str(source),
            "path": f"modules/{name}",
            "revision": "v1",
        }
        registry["modules"][name] = {
            "project": name,
            "revision": "v1",
            "metadata": f"modules/{name}/nsx-module.yaml",
        }
    cfg: dict[str, Any] = {"target": {"board": "apollo510_evb", "soc": "apollo510"}, "modules": []}
    return registry, cfg


def resolve(
    registry: dict[str, Any], cfg: dict[str, Any], seeds: list[str] | None = None
) -> list[str]:
    return _resolve_module_closure(
        seeds or ["parent"],
        app_dir=None,
        registry=registry,
        nsx_cfg=cfg,
        default_toolchain="arm-none-eabi-gcc",
    )


@pytest.mark.parametrize(
    ("bounds", "version", "accepted"),
    [
        (">=7.47.0,<8", "7.46.9", False),
        (">=7.47.0,<8", "7.47.0", True),
        (">=7.47.0,<8", "8.0", False),
        (">=1,<2", "1.5rc1", False),
        (">=1,<2", "1.5.dev1", False),
        (">=1rc1,<2", "1.5rc1", True),
        ("!=1rc1,>=1,<2", "1.5rc1", False),
        ("==1.0", "1.0+vendor.2", True),
        ("~=1.4.0", "1.5.0", False),
        ("==1.*", "1.7", True),
        (">=1", "opaque-build", False),
    ],
)
def test_version_outcomes(tmp_path: Path, bounds: str, version: str, accepted: bool) -> None:
    registry, cfg = project(
        tmp_path,
        [
            manifest("parent", required=[{"name": "dep", "version": bounds}]),
            manifest("dep", version),
        ],
    )
    if accepted:
        assert resolve(registry, cfg) == ["dep", "parent"]
    else:
        with pytest.raises(NSXModuleError, match="parent.*dep.*version"):
            resolve(registry, cfg)


@pytest.mark.parametrize(
    "entry",
    [
        1,
        None,
        {},
        {"name": ""},
        {"name": "dep", "version": None},
        {"name": "dep", "version": ""},
        {"name": "dep", "version": "^1"},
        {"name": "dep", "version": "===1"},
        {"name": "dep", "version": ">=1 || <3"},
        {"name": "dep", "extra": "x"},
    ],
)
def test_invalid_syntax(entry: object) -> None:
    with pytest.raises(ValueError):
        validate_nsx_module_metadata(manifest("parent", required=[entry]), "test.yaml")


def test_existing_strings_and_repeated_dependencies_remain_supported(tmp_path: Path) -> None:
    data = manifest("parent", required=["dep", "dep"])
    validate_nsx_module_metadata(data, "test.yaml")
    assert ModuleMetadata.from_raw(data).required_deps == ["dep", "dep"]
    registry, cfg = project(tmp_path, [data, manifest("dep", "custom-version")])
    assert resolve(registry, cfg) == ["dep", "parent"]


def test_every_parent_constraint_is_checked(tmp_path: Path) -> None:
    registry, cfg = project(
        tmp_path,
        [
            manifest("parent", required=["dep", "other"]),
            manifest("other", required=[{"name": "dep", "version": ">=2"}]),
            manifest("dep"),
        ],
    )
    with pytest.raises(NSXModuleError, match="other.*dep"):
        resolve(registry, cfg)


@pytest.mark.parametrize("version", [None, 123])
def test_structural_version_error_is_contextual(tmp_path: Path, version: object) -> None:
    dep = manifest("dep", version)
    if version is None:
        del dep["module"]["version"]
    registry, cfg = project(
        tmp_path, [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), dep]
    )
    with pytest.raises(NSXModuleError, match="parent.*dep.*invalid"):
        resolve(registry, cfg)
    with pytest.raises(NSXModuleError, match="parent.*dep.*invalid"):
        validate_materialized_requirements(
            ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )


def test_opaque_requires_metadata_only_for_constrained_edge(tmp_path: Path) -> None:
    registry, cfg = project(
        tmp_path, [manifest("parent", required=[{"name": "dep", "version": ">=1"}])]
    )
    cfg["modules"] = [{"name": "dep", "source": {"vendored": True}}]
    with pytest.raises(NSXModuleError, match="opaque"):
        resolve(registry, cfg)
    project(tmp_path, [manifest("parent", required=["dep"])])
    assert resolve(registry, cfg) == ["dep", "parent"]


def test_missing_locked_edge_rejected(tmp_path: Path) -> None:
    registry, cfg = project(tmp_path, [manifest("parent", required=["dep"])])
    with pytest.raises(NSXModuleError, match="absent from nsx.lock"):
        validate_materialized_requirements(
            ["parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )


def test_materialized_metadata_reloaded_between_checks(tmp_path: Path) -> None:
    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), manifest("dep")],
    )
    validate_materialized_requirements(
        ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
    )
    project(tmp_path, [manifest("dep", "0.9")])
    with pytest.raises(NSXModuleError, match="0.9"):
        validate_materialized_requirements(
            ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )


def test_discovery_preserves_names_and_constraints(tmp_path: Path) -> None:
    registry, _ = project(
        tmp_path, [manifest("parent", required=[{"name": "dep", "version": ">=1"}])]
    )
    record = _module_discovery_record("parent", registry)
    assert record.to_dict()["depends"] == {
        "required": ["dep"],
        "optional": [],
        "required_dependencies": [{"name": "dep", "version": ">=1"}],
    }


def locked_app(tmp_path: Path) -> Path:
    from neuralspotx.operations._lock import lock_app_impl

    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), manifest("dep")],
    )
    cfg.update({
        "schema_version": 2,
        "project": {"name": "testapp"},
        "baseline": "none",
        "modules": ["parent"],
        "module_registry": registry,
    })
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(cfg))
    lock_app_impl(tmp_path)
    return tmp_path


@pytest.mark.parametrize("operation", ["configure", "build", "flash"])
def test_existing_lock_rejects_incompatible_metadata_before_cmake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    from neuralspotx import operations, project_config
    from neuralspotx.operations import _build

    app = locked_app(tmp_path)
    project(tmp_path, [manifest("dep", "0.9")])
    build = app / "build" / "apollo510_evb"
    build.mkdir(parents=True, exist_ok=True)
    (build / "build.ninja").write_text("# existing build")
    monkeypatch.setattr(_build, "regenerate_active_board_glue", lambda *a, **k: None)
    monkeypatch.setattr(_build, "_flash_cache_matches", lambda *a, **k: True)
    # Leave real dependency validation and real metadata loading in place.
    monkeypatch.setattr(_build, "_ensure_app_modules", lambda *a, **k: None)

    def no_subprocess(*args: object, **kwargs: object) -> None:
        pytest.fail("CMake/build must not run after an incompatible dependency is detected")

    monkeypatch.setattr(_build, "run", no_subprocess)
    monkeypatch.setattr(_build, "run_capture", no_subprocess)
    monkeypatch.setattr(project_config, "run", no_subprocess)
    with pytest.raises(NSXModuleError, match="parent.*dep.*0.9"):
        getattr(operations, f"{operation}_app_impl")(app)


def test_sync_validates_after_materialization(tmp_path: Path) -> None:
    from neuralspotx.operations._sync import sync_app_impl

    app = locked_app(tmp_path)
    project(tmp_path, [manifest("dep", "0.9")])
    with pytest.raises(NSXModuleError, match="parent.*dep.*0.9"):
        sync_app_impl(app)


def test_materialization_does_not_reuse_outer_metadata_cache(tmp_path: Path) -> None:
    from neuralspotx.module_registry._metadata import metadata_cache_scope

    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), manifest("dep")],
    )
    with metadata_cache_scope():
        resolve(registry, cfg)
        project(tmp_path, [manifest("dep", "0.9")])
        with pytest.raises(NSXModuleError, match="0.9"):
            validate_materialized_requirements(
                ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
            )


def test_skip_compat_does_not_skip_version_bounds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NSX_SKIP_COMPAT_CHECK", "1")
    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=2"}]), manifest("dep")],
    )
    with pytest.raises(NSXModuleError, match="parent.*dep"):
        resolve(registry, cfg)


@pytest.mark.parametrize("bounds", [",", ", ,"])
def test_effectively_empty_constraint_rejected_from_yaml(tmp_path: Path, bounds: str) -> None:
    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": bounds}]), manifest("dep", "0.0")],
    )
    with pytest.raises(ValueError, match="at least one comparison"):
        resolve(registry, cfg)
    with pytest.raises(NSXModuleError, match="at least one comparison"):
        validate_materialized_requirements(
            ["parent", "dep"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )


def test_search_indexes_requirement_bounds(tmp_path: Path) -> None:
    from neuralspotx.module_discovery import _search_score

    registry, _ = project(
        tmp_path, [manifest("parent", required=[{"name": "dep", "version": ">=7.47.0,<8"}])]
    )
    record = _module_discovery_record("parent", registry)
    score, matches = _search_score(record, "7.47.0")
    assert score > 0
    assert any(match.field == "depends.required.version" for match in matches)


@pytest.mark.parametrize("raw", ["", "- list-root\n", "module: [unterminated\n"])
def test_malformed_dependency_yaml_keeps_incoming_context(tmp_path: Path, raw: str) -> None:
    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), manifest("dep")],
    )
    (tmp_path / "sources/dep/nsx-module.yaml").write_text(raw)
    (tmp_path / "modules/dep/nsx-module.yaml").write_text(raw)
    with pytest.raises(NSXModuleError, match="parent.*dep.*>=1.*invalid"):
        resolve(registry, cfg)
    with pytest.raises(NSXModuleError, match="parent.*dep.*>=1.*invalid"):
        validate_materialized_requirements(
            ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )


@pytest.mark.parametrize("new_edges", [["parent"], ["dep"], ["other"]])
def test_materialized_cycle_or_stale_order_is_rejected(
    tmp_path: Path, new_edges: list[object]
) -> None:
    registry, cfg = project(
        tmp_path, [manifest("parent", required=["dep"]), manifest("dep"), manifest("other")]
    )
    order = resolve(registry, cfg, ["parent", "other"])
    assert order == ["dep", "parent", "other"]
    project(tmp_path, [manifest("dep", required=new_edges)])
    with pytest.raises(NSXModuleError, match="stale order or dependency cycle"):
        validate_materialized_requirements(order, app_dir=tmp_path, nsx_cfg=cfg, registry=registry)


def test_cached_build_refuses_new_cycle_without_rewriting_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from neuralspotx.operations import _build

    app = locked_app(tmp_path)
    original_lock = (app / "nsx.lock").read_bytes()
    project(tmp_path, [manifest("dep", required=["parent"])])
    build = app / "build/apollo510_evb"
    (build / "build.ninja").write_text("# configured")
    monkeypatch.setattr(_build, "regenerate_active_board_glue", lambda *a, **k: None)

    def no_build(*args: object, **kwargs: object) -> None:
        pytest.fail("must reject cycle before build")

    monkeypatch.setattr(_build, "run", no_build)
    with pytest.raises(NSXModuleError, match="dependency cycle"):
        _build.build_app_impl(app)
    assert (app / "nsx.lock").read_bytes() == original_lock


@pytest.mark.parametrize(
    ("source_version", "copy_version", "accepted"), [("2.0", "1.0", False), ("1.0", "2.0", True)]
)
def test_cached_build_validates_compiled_copy_not_external_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_version: str,
    copy_version: str,
    accepted: bool,
) -> None:
    from neuralspotx.operations import _build

    app = locked_app(tmp_path)
    (app / "modules/parent/nsx-module.yaml").write_text(
        yaml.safe_dump(manifest("parent", required=[{"name": "dep", "version": ">=2"}]))
    )
    (app / "sources/dep/nsx-module.yaml").write_text(
        yaml.safe_dump(manifest("dep", source_version))
    )
    (app / "modules/dep/nsx-module.yaml").write_text(yaml.safe_dump(manifest("dep", copy_version)))
    (app / "build/apollo510_evb/build.ninja").write_text("# configured")
    calls: list[object] = []
    monkeypatch.setattr(_build, "run", lambda *a, **k: calls.append(a))
    if accepted:
        _build.build_app_impl(app)
        assert len(calls) == 1
    else:
        with pytest.raises(NSXModuleError, match="parent.*dep.*1.0"):
            _build.build_app_impl(app)
        assert calls == []


def test_materialized_missing_copy_never_falls_back_to_external_metadata(tmp_path: Path) -> None:
    registry, cfg = project(
        tmp_path,
        [manifest("parent", required=[{"name": "dep", "version": ">=1"}]), manifest("dep")],
    )
    (tmp_path / "modules/dep/nsx-module.yaml").unlink()
    assert resolve(registry, cfg) == ["dep", "parent"]
    with pytest.raises(NSXModuleError, match="parent.*dep.*Build-local metadata"):
        validate_materialized_requirements(
            ["dep", "parent"], app_dir=tmp_path, nsx_cfg=cfg, registry=registry
        )
