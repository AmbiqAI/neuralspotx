from __future__ import annotations

from neuralspotx.models import (
    AppConfig,
    CommandCategory,
    CommandHint,
    CommandScope,
    DiscoveryRecord,
    ModuleMetadata,
    ModuleRegistryOverride,
    SearchMatch,
    SearchResult,
)


def test_app_config_classifies_module_sources() -> None:
    cfg = AppConfig.from_mapping({
        "project": {"name": "demo"},
        "modules": [
            {"name": "nsx-uart", "project": "nsx-uart", "revision": "main"},
            {"name": "local-demo", "source": {"path": "../local-demo"}},
            {"name": "custom-aot", "source": {"vendored": True}},
        ],
    })

    assert cfg.project_name == "demo"
    assert cfg.module_names() == ["nsx-uart", "local-demo", "custom-aot"]
    assert cfg.local_module_names() == {"local-demo"}
    assert cfg.vendored_module_names() == {"custom-aot"}
    assert set(cfg.opaque_modules()) == {"local-demo", "custom-aot"}


def _module_metadata_raw() -> dict:
    return {
        "schema_version": 1,
        "module": {"name": "nsx-uart", "type": "runtime", "version": "1.2.3"},
        "support": {"ambiqsuite": True, "zephyr": False},
        "build": {"cmake": {"package": "nsx_uart", "targets": ["nsx-uart"]}},
        "depends": {"required": ["nsx-core"], "optional": ["nsx-dma"]},
        "compatibility": {
            "boards": ["apollo510_evb"],
            "socs": ["apollo510"],
            "toolchains": ["gcc"],
        },
        # Open-ended, agent-facing payload that must survive untyped.
        "capabilities": ["uart-tx", "uart-rx"],
        "agent_keywords": ["serial"],
        "constraints": {"required_sdk_provider": "ambiqsuite"},
    }


def test_module_metadata_typed_structural_accessors() -> None:
    meta = ModuleMetadata.from_raw(_module_metadata_raw())

    assert meta.name == "nsx-uart"
    assert meta.module_type == "runtime"
    assert meta.version == "1.2.3"
    assert meta.supports_ambiqsuite is True
    assert meta.required_deps == ["nsx-core"]
    assert meta.optional_deps == ["nsx-dma"]
    assert meta.compatibility["boards"] == ["apollo510_evb"]
    assert meta.required_sdk_provider == "ambiqsuite"


def test_module_metadata_preserves_open_ended_payload_in_raw() -> None:
    raw = _module_metadata_raw()
    meta = ModuleMetadata.from_raw(raw)

    # Semantic/discovery fields are intentionally not typed; they stay in raw
    # so newly authored keys keep flowing through unchanged.
    assert meta.raw is raw
    assert meta.raw["capabilities"] == ["uart-tx", "uart-rx"]
    assert meta.raw["agent_keywords"] == ["serial"]


def test_module_metadata_required_sdk_provider_absent_or_malformed() -> None:
    assert ModuleMetadata.from_raw({}).required_sdk_provider is None
    assert ModuleMetadata.from_raw({"constraints": []}).required_sdk_provider is None
    assert (
        ModuleMetadata.from_raw(
            {"constraints": {"required_sdk_provider": 3}}
        ).required_sdk_provider
        is None
    )


def test_module_registry_override_merges_valid_entries_only() -> None:
    base = {
        "projects": {"nsx-uart": {"url": "old", "revision": "main"}},
        "modules": {"nsx-uart": {"project": "nsx-uart", "revision": "main"}},
    }
    override = ModuleRegistryOverride.from_mapping({
        "projects": {
            "nsx-uart": {"url": "new"},
            3: {"url": "ignored"},
        },
        "modules": {
            "nsx-uart": {"metadata": "modules/nsx-uart/nsx-module.yaml"},
            "bad": "ignored",
        },
    })

    merged = override.merge_into(base)

    assert merged["projects"]["nsx-uart"] == {"url": "new", "revision": "main"}
    assert merged["modules"]["nsx-uart"] == {
        "project": "nsx-uart",
        "revision": "main",
        "metadata": "modules/nsx-uart/nsx-module.yaml",
    }
    assert 3 not in merged["projects"]
    assert "bad" not in merged["modules"]


def test_discovery_record_to_dict_core_only() -> None:
    record = DiscoveryRecord(
        name="nsx-core",
        project="nsx-core",
        revision="main",
        metadata="modules/nsx-core/nsx-module.yaml",
        enabled=False,
    )
    d = record.to_dict()
    assert d == {
        "name": "nsx-core",
        "project": "nsx-core",
        "revision": "main",
        "metadata": "modules/nsx-core/nsx-module.yaml",
        "enabled": False,
    }
    assert "metadata_available" not in d


def test_discovery_record_to_dict_with_metadata() -> None:
    record = DiscoveryRecord(
        name="nsx-uart",
        project="nsx-uart",
        revision="main",
        metadata="m.yaml",
        enabled=True,
        metadata_available=True,
        module={"name": "nsx-uart", "type": "library", "version": "1.0.0"},
        build={"cmake": {"targets": ["nsx-uart"]}},
        depends={"required": [], "optional": []},
        compatibility={"boards": ["*"], "socs": ["*"], "toolchains": ["*"]},
        summary="UART driver",
    )
    d = record.to_dict()
    assert d["metadata_available"] is True
    assert d["module"]["type"] == "library"
    assert d["summary"] == "UART driver"
    assert "support" not in d  # None values are omitted


def test_discovery_record_to_dict_with_error() -> None:
    record = DiscoveryRecord(
        name="nsx-bad",
        project="nsx-bad",
        revision="main",
        metadata=None,
        enabled=False,
        metadata_error="Could not load metadata.",
    )
    d = record.to_dict()
    assert d["metadata_available"] is False
    assert d["metadata_error"] == "Could not load metadata."
    assert "module" not in d


def test_search_result_from_record_and_to_dict() -> None:
    record = DiscoveryRecord(
        name="nsx-core",
        project="nsx-core",
        revision="main",
        metadata="m.yaml",
        enabled=False,
        metadata_available=True,
        module={"name": "nsx-core", "type": "core", "version": "0.1.0"},
        build={"cmake": {"targets": ["nsx-core"]}},
        depends={"required": [], "optional": []},
        compatibility={"boards": ["*"], "socs": ["*"], "toolchains": ["*"]},
    )
    match = SearchMatch(field="name", term="core", value="nsx-core")
    result = SearchResult.from_record(record, score=20, matches=(match,), compatible=True)
    assert result.name == "nsx-core"
    assert result.score == 20
    assert result.compatible is True
    assert len(result.matches) == 1
    assert result.matches[0].field == "name"

    d = result.to_dict()
    assert d["score"] == 20
    assert d["compatible"] is True
    assert d["matches"] == [{"field": "name", "term": "core", "value": "nsx-core"}]
    assert d["metadata_available"] is True


def test_command_hint_to_dict() -> None:
    hint = CommandHint(
        category=CommandCategory.BUILD,
        scope=CommandScope.APP,
        next_commands=("nsx flash", "nsx view"),
    )
    d = hint.to_dict()
    assert d == {
        "category": "build",
        "scope": "app",
        "next_commands": ["nsx flash", "nsx view"],
    }
    assert "alias_for" not in d


def test_command_hint_to_dict_with_alias() -> None:
    hint = CommandHint(
        category=CommandCategory.APP_CREATION,
        scope=CommandScope.APP,
        next_commands=("nsx configure",),
        alias_for="nsx create-app",
    )
    d = hint.to_dict()
    assert d["alias_for"] == "nsx create-app"
    assert d["category"] == "app-creation"


def test_command_category_and_scope_are_str_enums() -> None:
    assert CommandCategory.BUILD == "build"
    assert CommandScope.GLOBAL == "global"
    assert isinstance(CommandCategory.MODULES, str)
    assert isinstance(CommandScope.FILESYSTEM, str)
