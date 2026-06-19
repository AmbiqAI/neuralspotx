"""Metadata helpers for NSX module orchestration."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ModuleType(str, enum.Enum):
    """Kind of NSX module declared in ``nsx-module.yaml``.

    Mixed with ``str`` so existing code that compares
    ``module["type"] == "runtime"`` keeps working unchanged.
    """

    SDK_PROVIDER = "sdk_provider"
    SOC = "soc"
    BOARD = "board"
    RUNTIME = "runtime"
    PORTABLE_API = "portable_api"
    ALGORITHM = "algorithm"
    TOOLING = "tooling"
    BACKEND_SPECIFIC = "backend_specific"

    def __str__(self) -> str:  # pragma: no cover — trivial
        return self.value


SUPPORTED_MODULE_TYPES = frozenset(t.value for t in ModuleType)


@dataclass(frozen=True)
class RegistryModuleEntry:
    """One module entry from registry.lock.yaml."""

    name: str
    project: str
    revision: str
    metadata: str


def _expect_type(container: dict[str, Any], key: str, expected: type, ctx: str) -> Any:
    if key not in container:
        raise ValueError(f"{ctx}: missing required key '{key}'")
    value = container[key]
    if not isinstance(value, expected):
        raise ValueError(
            f"{ctx}: key '{key}' must be {expected.__name__}, got {type(value).__name__}"
        )
    return value


def _expect_optional_str(container: dict[str, Any], key: str, ctx: str) -> None:
    if key in container and not isinstance(container[key], str):
        raise ValueError(f"{ctx}: key '{key}' must be string when provided")


def _expect_optional_str_list(container: dict[str, Any], key: str, ctx: str) -> None:
    if key not in container:
        return
    value = container[key]
    if not isinstance(value, list):
        raise ValueError(f"{ctx}: key '{key}' must be list when provided")
    if not all(isinstance(item, str) for item in value):
        raise ValueError(f"{ctx}: key '{key}' must contain only strings")


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"YAML file does not exist: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse YAML at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be a mapping at {path}")
    return data


def _derive_starter_profiles(data: dict[str, Any]) -> dict[str, Any]:
    """Expand ``soc_families`` + ``board_profiles`` into full starter profiles.

    Each profile's SoC family comes from the first-class board descriptor, so
    the per-board module list is assembled from the family baseline plus the
    board's own ``nsx-board-<board>`` module and the shared ``core_modules`` —
    no per-board duplication in the lock.
    """

    from .board_descriptors import load_board

    defaults = _expect_type(data, "profile_defaults", dict, "registry.lock")
    default_toolchain = defaults.get("toolchain", "arm-none-eabi-gcc")
    default_channel = defaults.get("channel", "stable")
    default_core_modules = list(defaults.get("core_modules", []))

    families = _expect_type(data, "soc_families", dict, "registry.lock")
    board_profiles = _expect_type(data, "board_profiles", dict, "registry.lock")

    profiles: dict[str, Any] = {}
    for board, raw in board_profiles.items():
        entry = raw or {}
        if not isinstance(entry, dict):
            raise ValueError(f"registry.lock: board_profiles['{board}'] must be a mapping")
        descriptor = load_board(board)
        if descriptor is None:
            raise ValueError(
                f"registry.lock: board_profiles['{board}'] has no board descriptor "
                f"(expected src/neuralspotx/boards/{board}/board.yaml)"
            )
        family_key = descriptor.soc_family
        family = families.get(family_key)
        if family is None:
            raise ValueError(
                f"registry.lock: board '{board}' references unknown soc family "
                f"'{family_key}' (known: {sorted(families)})"
            )
        provider = family["provider"]
        revision = family["revision"]
        # ``project`` is the (consolidated SDK monorepo) repository that hosts
        # the provider module; it defaults to the provider module name for the
        # legacy one-repo-per-module layout.
        project = family.get("project", provider)
        # ``sdk_modules`` lists every module vendored by the SDK monorepo for
        # this family. Each is repointed at the monorepo project so that any
        # app pulling it resolves to the tier-correct source. Defaults to just
        # the provider for back-compat with split-repo families.
        sdk_modules = family.get("sdk_modules", [provider])
        # ``core_modules`` are appended after the board module for every
        # profile. A family may override the shared default (e.g. the
        # Apollo5 family whose runtime helpers add nsx-pmu-armv8m).
        core_modules = list(family.get("core_modules", default_core_modules))
        board_module = "nsx-board-" + board.replace("_", "-").lower()
        module_overrides = {
            name: {
                "project": project,
                "revision": revision,
                "metadata": f"modules/{name}/nsx-module.yaml",
            }
            for name in sdk_modules
        }
        profiles[f"{board}_minimal"] = {
            "board": board,
            "soc": descriptor.soc,
            "toolchain": entry.get("toolchain", default_toolchain),
            "channel": entry.get("channel", default_channel),
            "project_overrides": {project: {"revision": revision}},
            "module_overrides": module_overrides,
            "modules": [*family["modules"], board_module, *core_modules],
            "features": {},
        }
    return profiles


def load_registry_lock(path: Path) -> dict[str, Any]:
    data = load_yaml(path)
    schema_version = _expect_type(data, "schema_version", int, "registry.lock")
    if schema_version != 1:
        raise ValueError(f"registry.lock: unsupported schema_version={schema_version}, expected 1")
    _expect_type(data, "channels", dict, "registry.lock")
    _expect_type(data, "projects", dict, "registry.lock")
    _expect_type(data, "modules", dict, "registry.lock")
    # ``starter_profiles`` is derived from the family baselines + per-board
    # channel when those sections are present; otherwise it must be supplied
    # literally (used by tests that build minimal registries).
    if "soc_families" in data or "board_profiles" in data:
        data["starter_profiles"] = _derive_starter_profiles(data)
    _expect_type(data, "starter_profiles", dict, "registry.lock")
    return data


def validate_nsx_module_metadata(data: dict[str, Any], module_path: str) -> None:
    schema_version = _expect_type(data, "schema_version", int, module_path)
    if schema_version != 1:
        raise ValueError(f"{module_path}: unsupported schema_version={schema_version}, expected 1")

    module = _expect_type(data, "module", dict, module_path)
    module_name = _expect_type(module, "name", str, f"{module_path}.module")
    module_type = _expect_type(module, "type", str, f"{module_path}.module")
    _expect_type(module, "version", str, f"{module_path}.module")
    if "category" in module and not isinstance(module["category"], str):
        raise ValueError(f"{module_path}.module.category must be string when provided")
    if "provider" in module and not isinstance(module["provider"], str):
        raise ValueError(f"{module_path}.module.provider must be string when provided")
    if module_type not in SUPPORTED_MODULE_TYPES:
        raise ValueError(
            f"{module_path}: module.type='{module_type}' is not supported. "
            f"Allowed: {sorted(SUPPORTED_MODULE_TYPES)}"
        )

    support = _expect_type(data, "support", dict, module_path)
    ambiqsuite = _expect_type(support, "ambiqsuite", bool, f"{module_path}.support")
    zephyr = _expect_type(support, "zephyr", bool, f"{module_path}.support")
    if not ambiqsuite:
        raise ValueError(f"{module_path}: support.ambiqsuite=false is invalid for NSX modules")

    build = _expect_type(data, "build", dict, module_path)
    build_cmake = _expect_type(build, "cmake", dict, f"{module_path}.build")
    _expect_type(build_cmake, "package", str, f"{module_path}.build.cmake")
    targets = _expect_type(build_cmake, "targets", list, f"{module_path}.build.cmake")
    if not targets:
        raise ValueError(f"{module_path}: build.cmake.targets must not be empty")

    depends = _expect_type(data, "depends", dict, module_path)
    required = _expect_type(depends, "required", list, f"{module_path}.depends")
    _expect_type(depends, "optional", list, f"{module_path}.depends")
    for idx, dep_name in enumerate(required):
        if not isinstance(dep_name, str):
            raise ValueError(f"{module_path}: depends.required[{idx}] must be string module name")

    compatibility = _expect_type(data, "compatibility", dict, module_path)
    boards = _expect_type(compatibility, "boards", list, f"{module_path}.compatibility")
    socs = _expect_type(compatibility, "socs", list, f"{module_path}.compatibility")
    toolchains = _expect_type(compatibility, "toolchains", list, f"{module_path}.compatibility")
    for field_name, values in (
        ("boards", boards),
        ("socs", socs),
        ("toolchains", toolchains),
    ):
        if not values:
            raise ValueError(f"{module_path}: compatibility.{field_name} must not be empty")
        if not all(isinstance(item, str) for item in values):
            raise ValueError(f"{module_path}: compatibility.{field_name} must contain only strings")

    if zephyr:
        integrations = _expect_type(data, "integrations", dict, module_path)
        zephyr_cfg = _expect_type(integrations, "zephyr", dict, f"{module_path}.integrations")
        _expect_type(zephyr_cfg, "path", str, f"{module_path}.integrations.zephyr")
        _expect_type(zephyr_cfg, "module_yml", str, f"{module_path}.integrations.zephyr")
        _expect_type(zephyr_cfg, "kconfig", str, f"{module_path}.integrations.zephyr")

    if module_type == "board" and not required:
        raise ValueError(
            f"{module_path}: board module '{module_name}' must have required dependencies"
        )

    _expect_optional_str(data, "summary", module_path)
    for key in (
        "capabilities",
        "use_cases",
        "anti_use_cases",
        "agent_keywords",
        "example_refs",
        "composition_hints",
    ):
        _expect_optional_str_list(data, key, module_path)

    constraints = data.get("constraints", {})
    if constraints:
        if not isinstance(constraints, dict):
            raise ValueError(f"{module_path}: constraints must be mapping when provided")
        if "required_sdk_provider" in constraints and not isinstance(
            constraints["required_sdk_provider"], str
        ):
            raise ValueError(f"{module_path}: constraints.required_sdk_provider must be string")


def registry_entry_for_module(registry: dict[str, Any], module_name: str) -> RegistryModuleEntry:
    modules = registry["modules"]
    if module_name not in modules:
        raise ValueError(f"Module '{module_name}' not found in registry.lock")
    entry = modules[module_name]
    if not isinstance(entry, dict):
        raise ValueError(f"registry.lock: modules.{module_name} must be a mapping")
    project = _expect_type(entry, "project", str, f"registry.lock.modules.{module_name}")
    revision = _expect_type(entry, "revision", str, f"registry.lock.modules.{module_name}")
    metadata = _expect_type(entry, "metadata", str, f"registry.lock.modules.{module_name}")
    return RegistryModuleEntry(
        name=module_name,
        project=project,
        revision=revision,
        metadata=metadata,
    )


def is_compatible(
    metadata: dict[str, Any],
    *,
    board: str,
    soc: str,
    toolchain: str,
) -> bool:
    compat = metadata["compatibility"]

    def _ok(values: list[str], current: str) -> bool:
        return "*" in values or current in values

    return (
        _ok(compat["boards"], board)
        and _ok(compat["socs"], soc)
        and _ok(compat["toolchains"], toolchain)
    )
