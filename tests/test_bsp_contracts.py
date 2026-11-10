"""Custom board contracts tested at graph and frozen-build boundaries."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx._errors import NSXLockError, NSXModuleError
from neuralspotx.board_descriptors import BoardDescriptorError, load_board_for_app
from neuralspotx.bsp_contracts import BspBinding
from neuralspotx.metadata import validate_nsx_module_metadata
from neuralspotx.models._module_dependency import parse_required_dependencies
from neuralspotx.module_registry._closure import _resolve_module_closure
from neuralspotx.module_registry._composition import board_composition, verify_board_composition
from neuralspotx.operations._board import create_board_impl


def setup_graph(root: Path, *, local: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    create_board_impl(
        "custom_ap330", from_board="apollo330mP_evb", app_dir=root, bsp_module="custom-bsp"
    )
    registry: dict[str, Any] = {"projects": {}, "modules": {}}
    requirements: dict[str, list[object]] = {
        "consumer": [{"role": "bsp", "contracts": [2]}],
        "custom-bsp": ["hal"],
        "hal": [],
    }
    for name, required in requirements.items():
        data: dict[str, Any] = {
            "schema_version": 1,
            "module": {"name": name, "version": "1.0.0", "type": "runtime"},
            "support": {"ambiqsuite": True, "zephyr": False},
            "build": {"cmake": {"package": name, "targets": [f"nsx::{name}"]}},
            "depends": {"required": required, "optional": []},
            "compatibility": {"boards": ["*"], "socs": ["apollo330P"], "toolchains": ["*"]},
        }
        if name == "custom-bsp":
            data["contracts"] = {"provides": {"bsp": {"versions": [2], "socs": ["apollo330P"]}}}
        directory = root / "modules" / name
        directory.mkdir(parents=True)
        (directory / "nsx-module.yaml").write_text(yaml.safe_dump(data))
        registry["projects"][name] = {
            "local_path": str(directory),
            "path": f"modules/{name}",
            "revision": "local",
        }
        registry["modules"][name] = {
            "project": name,
            "revision": "local",
            "metadata": "nsx-module.yaml",
        }
    cfg: dict[str, Any] = {
        "target": {"board": "custom_ap330", "soc": "apollo330P"},
        "modules": [{"name": "custom-bsp", "local": True}] if local else [],
    }
    return registry, cfg


def resolve(root: Path, registry: dict[str, Any], cfg: dict[str, Any]) -> list[str]:
    return _resolve_module_closure(
        ["consumer"],
        app_dir=root,
        registry=registry,
        nsx_cfg=cfg,
        default_toolchain="arm-none-eabi-gcc",
    )


@pytest.mark.parametrize("local", [False, True])
def test_custom_bsp_dependency_is_transparent(tmp_path: Path, local: bool) -> None:
    registry, cfg = setup_graph(tmp_path, local=local)
    assert resolve(tmp_path, registry, cfg) == ["hal", "custom-bsp", "consumer"]
    raw = yaml.safe_load((tmp_path / "boards/custom_ap330/nsx-module.yaml").read_text())
    validate_nsx_module_metadata(raw, "board")


@pytest.mark.parametrize("kind", ["cycle", "version", "soc", "concrete"])
def test_incompatible_graph_fails(tmp_path: Path, kind: str) -> None:
    registry, cfg = setup_graph(tmp_path, local=True)
    path = tmp_path / "modules/custom-bsp/nsx-module.yaml"
    data = yaml.safe_load(path.read_text())
    if kind == "cycle":
        data["depends"]["required"] = ["consumer"]
    elif kind == "version":
        data["contracts"]["provides"]["bsp"]["versions"] = [1]
    elif kind == "soc":
        data["contracts"]["provides"]["bsp"]["socs"] = ["apollo510"]
    else:
        data["depends"]["required"] = ["nsx-ambiq-bsp"]
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(NSXModuleError):
        resolve(tmp_path, registry, cfg)


@pytest.mark.parametrize(
    "changed",
    [
        "boards/apollo330mP_evb/board.yaml",
        "boards/custom_ap330/board.yaml",
        "modules/custom-bsp/nsx-module.yaml",
        "modules/consumer/nsx-module.yaml",
    ],
)
def test_frozen_contract_inputs_detect_byte_changes(tmp_path: Path, changed: str) -> None:
    registry, cfg = setup_graph(tmp_path)
    names = resolve(tmp_path, registry, cfg)
    record = board_composition(tmp_path, cfg, registry, names)
    verify_board_composition(record, tmp_path, cfg, registry, names)
    path = tmp_path / changed
    path.write_text(path.read_text() + "\n# changed authored input\n")
    with pytest.raises(NSXLockError, match="composition changed"):
        verify_board_composition(record, tmp_path, cfg, registry, names)


@pytest.mark.parametrize("contracts", [[], [True], [0], [2, 2], "2", [2.0]])
def test_strict_requirement_versions(contracts: object) -> None:
    with pytest.raises(ValueError):
        parse_required_dependencies([{"role": "bsp", "contracts": contracts}], "test")


def test_cannot_inherit_binding_or_cycle(tmp_path: Path) -> None:
    setup_graph(tmp_path)
    path = tmp_path / "boards/custom_ap330/board.yaml"
    data = yaml.safe_load(path.read_text())
    data.pop("roles")
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(BoardDescriptorError, match="explicit provider"):
        load_board_for_app("custom_ap330", tmp_path)
    data["roles"] = {"bsp": BspBinding("custom-bsp", 2).to_dict()}
    data["inherits"] = "custom_ap330"
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(BoardDescriptorError, match="cycle"):
        load_board_for_app("custom_ap330", tmp_path)


def test_provider_local_dependencies_supply_real_version_metadata(tmp_path: Path) -> None:
    from neuralspotx.module_registry._requirements import validate_materialized_requirements

    registry, cfg = setup_graph(tmp_path, local=True)
    cfg["modules"].append({"name": "hal", "local": True})
    path = tmp_path / "modules/custom-bsp/nsx-module.yaml"
    data = yaml.safe_load(path.read_text())
    data["depends"]["required"] = [{"name": "hal", "version": ">=1.0"}]
    path.write_text(yaml.safe_dump(data))
    names = resolve(tmp_path, registry, cfg)
    assert names == ["hal", "custom-bsp", "consumer"]
    validate_materialized_requirements(names, app_dir=tmp_path, nsx_cfg=cfg, registry=registry)


def test_vendored_provider_wins_over_registry_source(tmp_path: Path) -> None:
    registry, cfg = setup_graph(tmp_path)
    cfg["modules"] = [{"name": "custom-bsp", "source": {"vendored": True}}]
    external = tmp_path / "external"
    external.mkdir()
    data = yaml.safe_load(
        (tmp_path / "modules/custom-bsp/nsx-module.yaml").read_text(encoding="utf-8")
    )
    data["contracts"]["provides"]["bsp"]["versions"] = [1]
    (external / "nsx-module.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    registry["projects"]["custom-bsp"]["local_path"] = str(external)
    names = resolve(tmp_path, registry, cfg)
    assert names == ["hal", "custom-bsp", "consumer"]
    record = board_composition(tmp_path, cfg, registry, names)
    verify_board_composition(record, tmp_path, cfg, registry, names)


def test_read_only_fallback_retains_only_unavailable_contract_inputs(tmp_path: Path) -> None:
    from neuralspotx._errors import NSXResolutionError

    registry, cfg = setup_graph(tmp_path)
    names = resolve(tmp_path, registry, cfg)
    record = board_composition(tmp_path, cfg, registry, names)
    (tmp_path / "modules/hal/nsx-module.yaml").unlink()
    with pytest.raises(NSXResolutionError):
        board_composition(tmp_path, cfg, registry, names)
    assert board_composition(tmp_path, cfg, registry, names, read_only_record=record) == record
    (tmp_path / "modules/consumer/nsx-module.yaml").unlink()
    assert board_composition(tmp_path, cfg, registry, names, read_only_record=record) == record
    provider = tmp_path / "modules/custom-bsp/nsx-module.yaml"
    provider.write_text(provider.read_text() + "\n# changed available input\n")
    assert board_composition(tmp_path, cfg, registry, names, read_only_record=record) != record
    provider.unlink()
    assert board_composition(tmp_path, cfg, registry, names, read_only_record=record) == record
    with pytest.raises(NSXResolutionError):
        verify_board_composition(record, tmp_path, cfg, registry, names)


def test_board_plan_normalizes_builtin_input_case(tmp_path: Path) -> None:
    from neuralspotx.board_plan import resolve_board_plan

    plan = resolve_board_plan(
        tmp_path,
        {"baseline": "none", "target": {"board": "APOLLO330MP_EVB", "soc": "APOLLO330P"}},
    )
    assert plan is not None
    assert plan.descriptor.name == "apollo330mP_evb"
    assert plan.descriptor.soc == "apollo330P"


def test_composition_ignores_checkout_line_endings(tmp_path: Path) -> None:
    registry, cfg = setup_graph(tmp_path)
    names = resolve(tmp_path, registry, cfg)
    paths = list(tmp_path.rglob("*.yaml"))
    for path in paths:
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    record = board_composition(tmp_path, cfg, registry, names)
    for path in paths:
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    verify_board_composition(record, tmp_path, cfg, registry, names)


@pytest.mark.parametrize("role_first", [False, True])
def test_local_bsp_dependency_versions_are_order_independent(
    tmp_path: Path, role_first: bool
) -> None:
    registry, cfg = setup_graph(tmp_path, local=True)
    cfg["modules"].append({"name": "hal", "local": True})
    path = tmp_path / "modules/consumer/nsx-module.yaml"
    data = yaml.safe_load(path.read_text())
    deps = [{"name": "hal", "version": ">=1"}, {"role": "bsp", "contracts": [2]}]
    data["depends"]["required"] = list(reversed(deps)) if role_first else deps
    path.write_text(yaml.safe_dump(data))
    assert resolve(tmp_path, registry, cfg) == ["hal", "custom-bsp", "consumer"]
    hal = tmp_path / "modules/hal/nsx-module.yaml"
    data = yaml.safe_load(hal.read_text())
    data["module"]["version"] = "0.9.0"
    hal.write_text(yaml.safe_dump(data))
    with pytest.raises(NSXModuleError, match="version"):
        resolve(tmp_path, registry, cfg)


def test_registered_local_bsp_preserves_nested_metadata(tmp_path: Path) -> None:
    registry, cfg = setup_graph(tmp_path, local=True)
    root = tmp_path / "external"
    (root / "nsx").mkdir(parents=True)
    (tmp_path / "modules/custom-bsp/nsx-module.yaml").rename(root / "nsx/nsx-module.yaml")
    registry["projects"]["custom-bsp"]["local_path"] = str(root)
    registry["modules"]["custom-bsp"]["metadata"] = "modules/custom-bsp/nsx/nsx-module.yaml"
    assert resolve(tmp_path, registry, cfg) == ["hal", "custom-bsp", "consumer"]


def test_custom_provider_can_be_registered_only_in_layer(tmp_path: Path) -> None:
    from neuralspotx.module_registry._profile import expand_profile_seeds
    from neuralspotx.project_config import _effective_registry, _load_registry

    local_registry, cfg = setup_graph(tmp_path)
    cfg["registry"] = {"layers": [{"inline": local_registry}]}
    registry = _load_registry()
    expanded = expand_profile_seeds(cfg, registry, app_dir=tmp_path)
    seeds = {entry["name"]: entry for entry in expanded["modules"]}
    assert seeds["custom-bsp"]["project"] == "custom-bsp"
    effective = _effective_registry(registry, expanded, app_dir=tmp_path)
    assert effective["projects"]["custom-bsp"]["local_path"] == str(tmp_path / "modules/custom-bsp")
    assert "custom-bsp" not in expanded["_profile_registry"]["modules"]


@pytest.mark.parametrize("metadata_style", ["relative", "absolute", "external"])
@pytest.mark.parametrize("change_dependencies", [False, True])
def test_locked_composition_uses_resolved_git_revision(
    tmp_path: Path, change_dependencies: bool, monkeypatch: pytest.MonkeyPatch, metadata_style: str
) -> None:
    import shutil
    import subprocess

    from neuralspotx.nsx_lock import LockKind, NsxLock, ResolvedModule, hash_tree
    from neuralspotx.operations._lock_composition import resolved_board_composition

    registry, cfg = setup_graph(tmp_path)
    cfg["modules"] = [{"name": "consumer"}]
    source = tmp_path / "upstream"
    shutil.copytree(tmp_path / "modules/custom-bsp", source)

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(source), *args], text=True).strip()

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    git("add", ".")
    git("commit", "-qm", "old metadata")
    path = source / "nsx-module.yaml"
    if change_dependencies:
        data = yaml.safe_load(path.read_text())
        data["depends"]["required"] = []
        path.write_text(yaml.safe_dump(data))
    else:
        path.write_text(path.read_text() + "\n# new revision\n")
    git("add", ".")
    git("commit", "-qm", "new metadata")
    commit = git("rev-parse", "HEAD")

    # Production rejects file URLs; this test substitutes only transport,
    # retaining real Git checkout and artifact verification without a network.
    def clone_local(url: str, destination: Path, revision: str) -> None:
        assert url == str(source)
        subprocess.run(["git", "clone", "-q", "--no-checkout", url, str(destination)], check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "-q", revision], check=True)

    monkeypatch.setattr("neuralspotx.operations._lock_composition.git_clone_at_commit", clone_local)
    project = registry["projects"]["custom-bsp"]
    project.pop("local_path")
    project["url"] = str(source)
    if metadata_style != "relative":
        metadata = tmp_path / "modules/custom-bsp/nsx-module.yaml"
        if metadata_style == "external":
            external = tmp_path / "external.yaml"
            shutil.copyfile(metadata, external)
            metadata = external
        registry["modules"]["custom-bsp"]["metadata"] = str(metadata)
    names = resolve(tmp_path, registry, cfg)
    assert names == ["hal", "custom-bsp", "consumer"]  # old checkout
    lock = NsxLock()
    for name in names:
        lock.modules[name] = ResolvedModule(
            project=name,
            kind=LockKind.GIT if name == "custom-bsp" else LockKind.LOCAL,
            constraint="main",
            vendored_at=f"modules/{name}",
            content_hash=hash_tree(source) if name == "custom-bsp" else "",
            acquired_at="",
            url=str(source) if name == "custom-bsp" else None,
            commit=commit if name == "custom-bsp" else None,
        )
    if metadata_style == "external":
        with pytest.raises(NSXLockError, match="inside its project checkout"):
            resolved_board_composition(tmp_path, cfg, registry, lock)
    elif change_dependencies:
        with pytest.raises(NSXLockError, match="Dependency graph changed"):
            resolved_board_composition(tmp_path, cfg, registry, lock)
    else:
        record = resolved_board_composition(tmp_path, cfg, registry, lock)
        shutil.copyfile(path, tmp_path / "modules/custom-bsp/nsx-module.yaml")
        verify_board_composition(record, tmp_path, cfg, registry, names)


@pytest.mark.parametrize("name,bsp", [("../invalid", None), ("valid", "invalid bsp")])
def test_board_identifier_errors_are_typed(tmp_path: Path, name: str, bsp: str | None) -> None:
    from neuralspotx._errors import NSXConfigError

    with pytest.raises(NSXConfigError):
        create_board_impl(name, from_board="apollo330mP_evb", app_dir=tmp_path, bsp_module=bsp)
    assert not (tmp_path / "boards").exists()


@pytest.mark.parametrize("writable", [False, True])
def test_unchanged_bsp_lock_preserves_timestamp(tmp_path: Path, writable: bool) -> None:
    from neuralspotx.operations._lock import _build_lock_for_app
    from neuralspotx.operations._lock_selection import LockInputs

    registry, cfg = setup_graph(tmp_path)
    cfg["project"] = {"name": "test"}
    cfg["module_registry"] = registry
    cfg["modules"] = [{"name": "consumer"}]
    (tmp_path / "nsx.yml").write_text(yaml.safe_dump(cfg))
    inputs = LockInputs(cfg, registry, resolve(tmp_path, registry, cfg), set(), set())
    first = _build_lock_for_app(tmp_path, prepared=inputs, write_side_effects=writable)
    first.generated_at = "2020-01-01T00:00:00Z"
    second = _build_lock_for_app(
        tmp_path, prepared=inputs, write_side_effects=writable, previous=first
    )
    assert second.board_composition == first.board_composition
    assert second.generated_at == first.generated_at


def test_local_bsp_malformed_yaml_is_typed(tmp_path: Path) -> None:
    registry, cfg = setup_graph(tmp_path, local=True)
    (tmp_path / "modules/custom-bsp/nsx-module.yaml").write_text("module: [invalid")
    with pytest.raises(NSXModuleError, match="nsx-module.yaml: invalid YAML"):
        resolve(tmp_path, registry, cfg)


def test_invalid_parent_board_identifier_is_typed(tmp_path: Path) -> None:
    from neuralspotx._errors import NSXConfigError

    with pytest.raises(NSXConfigError):
        create_board_impl("valid", from_board="../invalid", app_dir=tmp_path)
    assert not (tmp_path / "boards").exists()


def test_malformed_parent_board_yaml_is_typed(tmp_path: Path) -> None:
    from neuralspotx._errors import NSXConfigError

    parent = tmp_path / "boards/parent/board.yaml"
    parent.parent.mkdir(parents=True)
    parent.write_text("board: [invalid")
    with pytest.raises(NSXConfigError, match="board.yaml: invalid YAML"):
        create_board_impl("child", from_board="parent", app_dir=tmp_path)
    assert not (tmp_path / "boards/child").exists()
