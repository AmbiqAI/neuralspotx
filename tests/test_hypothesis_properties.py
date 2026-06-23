"""Hypothesis property-based tests for YAML round-trip & schema validation (H2)."""

from __future__ import annotations

import copy

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from neuralspotx._errors import NSXConfigError
from neuralspotx.models._loader import NsxProject
from neuralspotx.models._project import AppModule, ModuleRegistryOverride, ModuleSource
from neuralspotx.nsx_lock._kinds import LockKind
from neuralspotx.nsx_lock._constants import LOCK_SCHEMA_VERSION
from neuralspotx.nsx_lock._models import NsxLock, ResolvedModule

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(categories=("L", "N", "P", "S", "Z"), exclude_characters="\x00"),
    min_size=1,
    max_size=30,
)
_identifier = st.from_regex(r"[a-z][a-z0-9_-]{0,29}", fullmatch=True)
_optional_text = st.one_of(st.none(), _safe_text)

_module_source_strategy = st.builds(
    ModuleSource,
    path=st.one_of(st.none(), _identifier),
    vendored=st.booleans(),
    extra=st.one_of(st.none(), st.dictionaries(_identifier, _safe_text, max_size=3)),
)

_app_module_strategy = st.builds(
    AppModule,
    name=_identifier,
    project=st.one_of(st.none(), _identifier),
    revision=st.one_of(st.none(), _identifier),
    local=st.booleans(),
    source=_module_source_strategy,
    extra=st.one_of(st.none(), st.dictionaries(_identifier, _safe_text, max_size=3)),
)

_lock_kind_strategy = st.sampled_from(list(LockKind))

_resolved_module_strategy = st.builds(
    ResolvedModule,
    project=_identifier,
    kind=_lock_kind_strategy,
    constraint=_safe_text,
    vendored_at=_safe_text,
    content_hash=_safe_text,
    acquired_at=_safe_text,
    url=_optional_text,
    tag=_optional_text,
    commit=_optional_text,
    tool_version=_optional_text,
)


# ---------------------------------------------------------------------------
# ModuleSource round-trip
# ---------------------------------------------------------------------------


class TestModuleSourceRoundTrip:
    @given(source=_module_source_strategy)
    @settings(max_examples=200)
    def test_to_from_mapping_preserves_core_fields(self, source: ModuleSource) -> None:
        mapping = source.to_mapping()
        rebuilt = ModuleSource.from_mapping(mapping)
        assert rebuilt.path == source.path
        assert rebuilt.vendored == source.vendored

    @given(source=_module_source_strategy)
    @settings(max_examples=100)
    def test_from_mapping_always_returns_module_source(self, source: ModuleSource) -> None:
        mapping = source.to_mapping()
        rebuilt = ModuleSource.from_mapping(mapping)
        assert isinstance(rebuilt, ModuleSource)


# ---------------------------------------------------------------------------
# AppModule round-trip
# ---------------------------------------------------------------------------


class TestAppModuleRoundTrip:
    @given(module=_app_module_strategy)
    @settings(max_examples=200)
    def test_to_from_mapping_preserves_name(self, module: AppModule) -> None:
        mapping = module.to_mapping()
        rebuilt = AppModule.from_mapping(0, mapping)
        assert rebuilt.name == module.name

    @given(module=_app_module_strategy)
    @settings(max_examples=200)
    def test_to_from_mapping_preserves_core_fields(self, module: AppModule) -> None:
        mapping = module.to_mapping()
        rebuilt = AppModule.from_mapping(0, mapping)
        assert rebuilt.project == module.project
        assert rebuilt.revision == module.revision
        assert rebuilt.local == module.local
        assert rebuilt.source.path == module.source.path
        assert rebuilt.source.vendored == module.source.vendored

    @given(module=_app_module_strategy)
    @settings(max_examples=100)
    def test_derived_properties_consistent(self, module: AppModule) -> None:
        assert module.is_local == (module.local or module.source.path is not None)
        assert module.is_vendored == module.source.vendored
        assert module.is_opaque == (module.is_local or module.is_vendored)


# ---------------------------------------------------------------------------
# ResolvedModule round-trip
# ---------------------------------------------------------------------------


class TestResolvedModuleRoundTrip:
    @given(mod=_resolved_module_strategy)
    @settings(max_examples=200)
    def test_to_from_yaml_dict_preserves_project_and_kind(self, mod: ResolvedModule) -> None:
        d = mod.to_yaml_dict()
        rebuilt = ResolvedModule.from_yaml_dict("test", d)
        assert rebuilt.project == mod.project
        assert rebuilt.kind == mod.kind

    @given(mod=_resolved_module_strategy)
    @settings(max_examples=200)
    def test_to_from_yaml_dict_preserves_constraint(self, mod: ResolvedModule) -> None:
        d = mod.to_yaml_dict()
        rebuilt = ResolvedModule.from_yaml_dict("test", d)
        assert rebuilt.constraint == mod.constraint

    @given(mod=_resolved_module_strategy)
    @settings(max_examples=200)
    def test_to_yaml_dict_has_required_keys(self, mod: ResolvedModule) -> None:
        d = mod.to_yaml_dict()
        assert "project" in d
        assert "kind" in d
        assert "constraint" in d
        assert "resolved" in d


# ---------------------------------------------------------------------------
# NsxLock round-trip
# ---------------------------------------------------------------------------


_nsx_lock_strategy = st.builds(
    NsxLock,
    schema_version=st.just(LOCK_SCHEMA_VERSION),
    generated_at=_safe_text,
    nsx_tool_version=_optional_text,
    manifest_path=st.just("nsx.yml"),
    manifest_hash=_safe_text,
    target=st.dictionaries(_identifier, _safe_text, max_size=3),
    modules=st.dictionaries(_identifier, _resolved_module_strategy, max_size=5),
    path=st.none(),
)


class TestNsxLockRoundTrip:
    @given(lock=_nsx_lock_strategy)
    @settings(max_examples=100)
    def test_to_from_yaml_dict_preserves_schema_version(self, lock: NsxLock) -> None:
        d = lock.to_yaml_dict()
        rebuilt = NsxLock.from_yaml_dict(d)
        assert rebuilt.schema_version == lock.schema_version

    @given(lock=_nsx_lock_strategy)
    @settings(max_examples=100)
    def test_to_from_yaml_dict_preserves_target(self, lock: NsxLock) -> None:
        d = lock.to_yaml_dict()
        rebuilt = NsxLock.from_yaml_dict(d)
        assert rebuilt.target == lock.target

    @given(lock=_nsx_lock_strategy)
    @settings(max_examples=100)
    def test_to_from_yaml_dict_preserves_module_count(self, lock: NsxLock) -> None:
        d = lock.to_yaml_dict()
        rebuilt = NsxLock.from_yaml_dict(d)
        assert set(rebuilt.modules.keys()) == set(lock.modules.keys())


# ---------------------------------------------------------------------------
# LockKind enum exhaustive
# ---------------------------------------------------------------------------


class TestLockKindEnum:
    @given(kind=_lock_kind_strategy)
    def test_str_roundtrip(self, kind: LockKind) -> None:
        assert LockKind(str(kind)) == kind

    @given(kind=_lock_kind_strategy)
    def test_value_is_lowercase(self, kind: LockKind) -> None:
        assert kind.value == kind.value.lower()


# ---------------------------------------------------------------------------
# NsxProject.from_mapping schema rejection
# ---------------------------------------------------------------------------


def _minimal_nsx_mapping(
    *,
    name: str = "my_app",
    board: str = "apollo510_evb",
) -> dict:
    return {
        "schema_version": 2,
        "project": {"name": name},
        "target": {"board": board},
        "modules": [],
    }


class TestNsxProjectSchemaRejection:
    def test_minimal_mapping_accepted(self) -> None:
        m = _minimal_nsx_mapping()
        proj = NsxProject.from_mapping(m)
        assert proj.project_name == "my_app"

    @given(bad_version=st.integers().filter(lambda x: x != 2))
    @settings(max_examples=50)
    def test_rejects_wrong_schema_version(self, bad_version: int) -> None:
        m = _minimal_nsx_mapping()
        m["schema_version"] = bad_version
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "schema_version"

    @given(
        bad_value=st.one_of(
            st.text(min_size=1, max_size=10),
            st.lists(st.integers(), max_size=3),
            st.booleans(),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_int_schema_version(self, bad_value) -> None:
        m = _minimal_nsx_mapping()
        m["schema_version"] = bad_value
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "schema_version"

    @given(
        bad_project=st.one_of(
            st.text(min_size=1, max_size=10),
            st.integers(),
            st.lists(st.integers(), max_size=3),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_mapping_project(self, bad_project) -> None:
        m = _minimal_nsx_mapping()
        m["project"] = bad_project
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "project"

    @given(
        bad_name=st.one_of(
            st.integers(),
            st.lists(st.text(max_size=5), max_size=3),
            st.just(None),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_string_project_name(self, bad_name) -> None:
        m = _minimal_nsx_mapping()
        m["project"]["name"] = bad_name
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "project.name"

    @given(
        bad_modules=st.one_of(
            st.text(min_size=1, max_size=10),
            st.integers(),
            st.dictionaries(st.text(max_size=5), st.integers(), max_size=2),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_list_modules(self, bad_modules) -> None:
        m = _minimal_nsx_mapping()
        m["modules"] = bad_modules
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "modules"

    def test_missing_schema_version_rejected(self) -> None:
        m = _minimal_nsx_mapping()
        del m["schema_version"]
        with pytest.raises(NSXConfigError) as exc_info:
            NsxProject.from_mapping(m)
        assert exc_info.value.field == "schema_version"


# ---------------------------------------------------------------------------
# NsxProject round-trip (from_mapping -> to_mapping -> from_mapping)
# ---------------------------------------------------------------------------


_nsx_project_mapping_strategy = st.fixed_dictionaries(
    {
        "schema_version": st.just(2),
        "project": st.fixed_dictionaries({"name": _identifier}),
        "target": st.fixed_dictionaries(
            {"board": _identifier},
            optional={"soc": _identifier},
        ),
        "modules": st.lists(
            st.fixed_dictionaries(
                {"name": _identifier},
                optional={
                    "project": _identifier,
                    "revision": _identifier,
                },
            ),
            max_size=5,
        ),
    },
    optional={
        "toolchain": _identifier,
    },
)


class TestNsxProjectRoundTrip:
    @given(mapping=_nsx_project_mapping_strategy)
    @settings(max_examples=100)
    def test_from_to_mapping_preserves_schema_version(self, mapping: dict) -> None:
        m = copy.deepcopy(mapping)
        proj = NsxProject.from_mapping(m)
        out = proj.to_mapping()
        proj2 = NsxProject.from_mapping(out)
        assert proj2.schema_version == proj.schema_version

    @given(mapping=_nsx_project_mapping_strategy)
    @settings(max_examples=100)
    def test_from_to_mapping_preserves_project_name(self, mapping: dict) -> None:
        m = copy.deepcopy(mapping)
        proj = NsxProject.from_mapping(m)
        out = proj.to_mapping()
        proj2 = NsxProject.from_mapping(out)
        assert proj2.project_name == proj.project_name

    @given(mapping=_nsx_project_mapping_strategy)
    @settings(max_examples=100)
    def test_from_to_mapping_preserves_module_count(self, mapping: dict) -> None:
        m = copy.deepcopy(mapping)
        proj = NsxProject.from_mapping(m)
        out = proj.to_mapping()
        proj2 = NsxProject.from_mapping(out)
        assert len(proj2.modules) == len(proj.modules)

    @given(mapping=_nsx_project_mapping_strategy)
    @settings(max_examples=100)
    def test_from_to_mapping_preserves_toolchain(self, mapping: dict) -> None:
        m = copy.deepcopy(mapping)
        proj = NsxProject.from_mapping(m)
        out = proj.to_mapping()
        proj2 = NsxProject.from_mapping(out)
        assert proj2.toolchain == proj.toolchain


# ---------------------------------------------------------------------------
# ModuleRegistryOverride merge_into property tests
# ---------------------------------------------------------------------------


_registry_strategy = st.fixed_dictionaries({
    "projects": st.dictionaries(
        _identifier,
        st.dictionaries(_identifier, _safe_text, max_size=2),
        max_size=3,
    ),
    "modules": st.dictionaries(
        _identifier,
        st.dictionaries(_identifier, _safe_text, max_size=2),
        max_size=3,
    ),
})


class TestModuleRegistryOverrideMerge:
    @given(override_data=_registry_strategy, base=_registry_strategy)
    @settings(max_examples=100)
    def test_merge_preserves_all_override_keys(self, override_data: dict, base: dict) -> None:
        override = ModuleRegistryOverride.from_mapping(override_data)
        merged = override.merge_into(base)
        for name in override.projects:
            assert name in merged["projects"]
        for name in override.modules:
            assert name in merged["modules"]

    @given(override_data=_registry_strategy, base=_registry_strategy)
    @settings(max_examples=100)
    def test_merge_preserves_base_disjoint_keys(self, override_data: dict, base: dict) -> None:
        override = ModuleRegistryOverride.from_mapping(override_data)
        merged = override.merge_into(base)
        for name in base.get("projects", {}):
            assert name in merged["projects"]
        for name in base.get("modules", {}):
            assert name in merged["modules"]

    def test_empty_override_is_identity(self) -> None:
        base = {"projects": {"p1": {"url": "https://x"}}, "modules": {"m1": {"project": "p1"}}}
        override = ModuleRegistryOverride.from_mapping(None)
        merged = override.merge_into(base)
        assert merged == base


# ---------------------------------------------------------------------------
# AppModule.from_mapping rejects non-mapping entries
# ---------------------------------------------------------------------------


class TestAppModuleSchemaRejection:
    @given(
        bad_entry=st.one_of(
            st.just(""),
            st.integers(),
            st.lists(st.integers(), max_size=3),
            st.just(None),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_mapping_entries(self, bad_entry) -> None:
        with pytest.raises(NSXConfigError) as exc_info:
            AppModule.from_mapping(0, bad_entry)
        assert "modules[0]" in (exc_info.value.field or "")

    @given(
        bad_name=st.one_of(
            st.integers(),
            st.lists(st.text(max_size=5), max_size=3),
            st.just(None),
        )
    )
    @settings(max_examples=50)
    def test_rejects_non_string_name(self, bad_name) -> None:
        with pytest.raises(NSXConfigError) as exc_info:
            AppModule.from_mapping(0, {"name": bad_name})
        assert "name" in (exc_info.value.field or "")
