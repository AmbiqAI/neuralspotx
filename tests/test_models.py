from __future__ import annotations

from neuralspotx.models import AppConfig, ModuleRegistryOverride


def test_app_config_classifies_module_sources() -> None:
    cfg = AppConfig.from_mapping(
        {
            "project": {"name": "demo"},
            "modules": [
                {"name": "nsx-uart", "project": "nsx-uart", "revision": "main"},
                {"name": "local-demo", "source": {"path": "../local-demo"}},
                {"name": "custom-aot", "source": {"vendored": True}},
            ],
        }
    )

    assert cfg.project_name == "demo"
    assert cfg.module_names() == ["nsx-uart", "local-demo", "custom-aot"]
    assert cfg.local_module_names() == {"local-demo"}
    assert cfg.vendored_module_names() == {"custom-aot"}
    assert set(cfg.opaque_modules()) == {"local-demo", "custom-aot"}


def test_module_registry_override_merges_valid_entries_only() -> None:
    base = {
        "projects": {"nsx-uart": {"url": "old", "revision": "main"}},
        "modules": {"nsx-uart": {"project": "nsx-uart", "revision": "main"}},
    }
    override = ModuleRegistryOverride.from_mapping(
        {
            "projects": {
                "nsx-uart": {"url": "new"},
                3: {"url": "ignored"},
            },
            "modules": {
                "nsx-uart": {"metadata": "modules/nsx-uart/nsx-module.yaml"},
                "bad": "ignored",
            },
        }
    )

    merged = override.merge_into(base)

    assert merged["projects"]["nsx-uart"] == {"url": "new", "revision": "main"}
    assert merged["modules"]["nsx-uart"] == {
        "project": "nsx-uart",
        "revision": "main",
        "metadata": "modules/nsx-uart/nsx-module.yaml",
    }
    assert 3 not in merged["projects"]
    assert "bad" not in merged["modules"]
