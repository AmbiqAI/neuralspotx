from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml

import neuralspotx.module_discovery as module_discovery
import neuralspotx.operations as operations
from neuralspotx import (
    AppBuildRequest,
    AppCleanRequest,
    AppCreateRequest,
    ModuleInitRequest,
    ModuleRegisterRequest,
    add_module,
    build_app,
    clean_app,
    cli,
    create_app,
    init_module,
    register_module,
    remove_module,
    update_modules,
)
from neuralspotx.project_config import (
    _load_app_cfg,
    _vendored_metadata_relpath,
    _vendored_target_dir,
)


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_local_module_metadata(path: Path, module_name: str = "local-demo") -> None:
    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "module:",
                f"  name: {module_name}",
                "  type: runtime",
                '  version: "0.1.0"',
                "support:",
                "  ambiqsuite: true",
                "  zephyr: false",
                "build:",
                "  cmake:",
                "    package: local_demo",
                "    targets: [local_demo]",
                "depends:",
                "  required: []",
                "  optional: []",
                "compatibility:",
                '  boards: ["*"]',
                '  socs: ["*"]',
                '  toolchains: ["arm-none-eabi-gcc"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _write_local_module_project(root: Path, module_name: str = "local-demo") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    metadata_path = root / "nsx-module.yaml"
    _write_local_module_metadata(metadata_path, module_name=module_name)
    (root / "CMakeLists.txt").write_text("add_library(local_demo INTERFACE)\n", encoding="utf-8")
    (root / "README.md").write_text("version one\n", encoding="utf-8")
    return metadata_path


def _write_searchable_module_metadata(
    path: Path,
    *,
    module_name: str,
    module_type: str = "runtime",
    summary: str | None = None,
    capabilities: list[str] | None = None,
    use_cases: list[str] | None = None,
    features: list[str] | None = None,
    socs: list[str] | None = None,
) -> None:
    capabilities = capabilities or []
    features = features or []
    socs = socs or ["*"]
    use_cases = use_cases or []
    quoted_socs = ", ".join(f'"{item}"' for item in socs)
    lines = [
        "schema_version: 1",
        "module:",
        f"  name: {module_name}",
        f"  type: {module_type}",
        '  version: "0.1.0"',
        "support:",
        "  ambiqsuite: true",
        "  zephyr: false",
        "build:",
        "  cmake:",
        f"    package: {module_name.replace('-', '_')}",
        f"    targets: [{module_name.replace('-', '_')}]",
        "depends:",
        "  required: []",
        "  optional: []",
        "compatibility:",
        '  boards: ["*"]',
        f"  socs: [{quoted_socs}]",
        '  toolchains: ["arm-none-eabi-gcc"]',
    ]
    if summary:
        lines.extend(
            [
                f"summary: {summary}",
            ]
        )
    if capabilities:
        lines.extend(
            [
                "capabilities:",
                *[f"  - {capability}" for capability in capabilities],
            ]
        )
    if use_cases:
        lines.extend(
            [
                "use_cases:",
                *[f"  - {use_case}" for use_case in use_cases],
            ]
        )
    if features:
        lines.extend(
            [
                "provides:",
                "  features:",
                *[f"    - {feature}" for feature in features],
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fake_registry_for_module(metadata_path: Path, module_name: str = "local-demo") -> dict:
    return {
        "schema_version": 1,
        "channels": {"stable": {"default": True}},
        "projects": {
            "local-demo-proj": {
                "name": "local-demo-proj",
                "path": "modules/local-demo",
            }
        },
        "modules": {
            module_name: {
                "project": "local-demo-proj",
                "revision": "main",
                "metadata": str(metadata_path),
            }
        },
        "starter_profiles": {},
        "compat_matrix": {},
    }


def test_app_major_version_mismatch_requires_bypass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_app(
        AppCreateRequest(
            app_dir=tmp_path / "hello_version", board="apollo510_evb", no_bootstrap=True
        )
    )

    app_dir = tmp_path / "hello_version"
    cfg_path = app_dir / "nsx.yml"
    cfg = _load_yaml(cfg_path)
    cfg["tooling"]["nsx"]["version"] = "0.1.0"
    cfg["tooling"]["nsx"]["major"] = 0
    cfg_path.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")

    monkeypatch.setattr("neuralspotx.project_config._nsx_tool_version", lambda: "1.2.3")
    monkeypatch.delenv("NSX_ALLOW_VERSION_MISMATCH", raising=False)

    with pytest.raises(SystemExit, match="NSX_ALLOW_VERSION_MISMATCH=1"):
        _ = _load_app_cfg(app_dir)

    monkeypatch.setenv("NSX_ALLOW_VERSION_MISMATCH", "1")
    loaded = _load_app_cfg(app_dir)
    assert loaded["project"]["name"] == "hello_version"


def test_vendored_module_metadata_path_stays_under_single_modules_root(tmp_path: Path) -> None:
    relpath = _vendored_metadata_relpath("modules/nsx-core/nsx-module.yaml")
    assert relpath == Path("modules") / "nsx-core" / "nsx-module.yaml"
    assert _vendored_target_dir(tmp_path, "nsx-core", "modules/nsx-core/nsx-module.yaml") == (
        tmp_path / "modules" / "nsx-core"
    )


def test_register_local_module_persists_relative_metadata_path(tmp_path: Path) -> None:
    create_app(
        AppCreateRequest(app_dir=tmp_path / "hello_local", board="apollo510_evb", no_bootstrap=True)
    )

    app_dir = tmp_path / "hello_local"
    metadata_path = app_dir / "local-module.yaml"
    _write_local_module_metadata(metadata_path)

    register_module(
        ModuleRegisterRequest(
            app_dir=app_dir,
            module="local-demo",
            metadata=metadata_path,
            project="local-demo-proj",
            project_local_path=app_dir,
        )
    )

    cfg = _load_yaml(app_dir / "nsx.yml")
    assert cfg["module_registry"]["modules"]["local-demo"]["metadata"] == "local-module.yaml"
    assert not (app_dir / "modules" / "local-demo").exists()


def test_cmd_module_list_json_outputs_structured_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata_path = _write_local_module_project(tmp_path / "modules" / "local-demo")
    monkeypatch.setattr(
        module_discovery, "_load_registry", lambda: _fake_registry_for_module(metadata_path)
    )

    cli.cmd_module_list(
        argparse.Namespace(
            app_dir=None,
            registry_only=True,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "packaged"
    assert [item["name"] for item in payload["modules"]] == ["local-demo"]
    assert payload["modules"][0]["module"]["type"] == "runtime"
    assert payload["modules"][0]["build"]["cmake"]["targets"] == ["local_demo"]


def test_cmd_module_describe_json_uses_app_effective_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    metadata_path = _write_local_module_project(tmp_path / "modules" / "local-demo")
    app_dir = tmp_path / "apps" / "demo"
    app_dir.mkdir(parents=True)

    monkeypatch.setattr(
        module_discovery, "_load_registry", lambda: _fake_registry_for_module(metadata_path)
    )
    monkeypatch.setattr(
        module_discovery,
        "_load_app_cfg",
        lambda _app_dir: {"modules": [{"name": "local-demo"}], "module_registry": {}},
    )

    cli.cmd_module_describe(
        argparse.Namespace(
            module="local-demo",
            app_dir=str(app_dir),
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["scope"] == "app-effective"
    assert payload["app_dir"] == str(app_dir.resolve())
    assert payload["module"]["enabled"] is True
    assert payload["module"]["depends"]["required"] == []


def test_module_describe_parser_wiring() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(["module", "describe", "local-demo", "--json"])

    assert args.module == "local-demo"
    assert args.json is True
    assert args.app_dir is None
    assert args.func == cli.cmd_module_describe


def test_module_init_creates_valid_skeleton(tmp_path: Path) -> None:
    module_dir = tmp_path / "my-sensor-driver"

    init_module(
        ModuleInitRequest(
            module_dir=module_dir,
            module_type="backend_specific",
            summary="I2C driver for the XYZ ambient light sensor.",
            dependencies=["nsx-core", "nsx-i2c"],
            socs=["apollo510", "apollo510b", "apollo5b"],
        )
    )

    metadata_path = module_dir / "nsx-module.yaml"
    header_path = module_dir / "includes-api" / "my_sensor_driver" / "my_sensor_driver.h"
    source_path = module_dir / "src" / "my_sensor_driver.c"
    cmake_path = module_dir / "CMakeLists.txt"

    assert metadata_path.exists()
    assert header_path.exists()
    assert source_path.exists()
    assert cmake_path.exists()

    metadata = _load_yaml(metadata_path)
    assert metadata["module"]["name"] == "my-sensor-driver"
    assert metadata["module"]["type"] == "backend_specific"
    assert metadata["depends"]["required"] == ["nsx-core", "nsx-i2c"]
    assert metadata["compatibility"]["socs"] == ["apollo510", "apollo510b", "apollo5b"]

    cmake_text = cmake_path.read_text(encoding="utf-8")
    assert "find_package(nsx_core REQUIRED)" in cmake_text
    assert "find_package(nsx_i2c REQUIRED)" in cmake_text
    assert "add_library(nsx::my_sensor_driver ALIAS my_sensor_driver)" in cmake_text

    header_text = header_path.read_text(encoding="utf-8")
    assert "MY_SENSOR_DRIVER_H" in header_text
    assert "int my_sensor_driver_init(void);" in header_text


def test_module_init_parser_wiring() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(
        [
            "module",
            "init",
            "my-sensor-driver",
            "--type",
            "backend_specific",
            "--dependency",
            "nsx-core",
            "--soc",
            "apollo510",
        ]
    )

    assert args.module_dir == "my-sensor-driver"
    assert args.type == "backend_specific"
    assert args.dependency == ["nsx-core"]
    assert args.soc == ["apollo510"]
    assert args.func == cli.cmd_module_init


def test_cmd_commands_json_outputs_command_graph(
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli.cmd_commands(argparse.Namespace(json=True))

    payload = json.loads(capsys.readouterr().out)
    top_level = {item["command"]: item for item in payload["commands"]}

    assert payload["command"] == "nsx"
    assert "nsx create-app" in payload["workflow"]["recommended_start"]
    assert "nsx commands" in top_level
    assert top_level["nsx create-app"]["category"] == "app-creation"
    assert "nsx configure" in top_level["nsx create-app"]["next_commands"]

    module_subcommands = {item["command"]: item for item in top_level["nsx module"]["subcommands"]}
    assert "nsx module describe" in module_subcommands
    assert "nsx module init" in module_subcommands
    assert any(
        option["flags"] == ["--json"]
        for option in module_subcommands["nsx module describe"]["arguments"]["options"]
    )


def test_commands_parser_wiring() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(["commands", "--json"])

    assert args.json is True
    assert args.func == cli.cmd_commands


def test_cmd_module_search_json_matches_capability_terms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pmu_root = tmp_path / "modules" / "pmu-demo"
    perf_root = tmp_path / "modules" / "perf-demo"
    pmu_root.mkdir(parents=True)
    perf_root.mkdir(parents=True)
    _write_searchable_module_metadata(
        pmu_root / "nsx-module.yaml",
        module_name="pmu-demo",
        summary="Armv8-M PMU profiling helpers",
        capabilities=["pmu", "profiling", "counters"],
        use_cases=["function profiling", "cycle analysis"],
        features=["pmu", "profiling", "counters"],
        socs=["apollo510"],
    )
    _write_searchable_module_metadata(
        perf_root / "nsx-module.yaml",
        module_name="perf-demo",
        summary="Generic performance timing helpers",
        capabilities=["profiling", "timing"],
        features=["profiling", "timing"],
        socs=["apollo4p"],
    )

    registry = {
        "schema_version": 1,
        "channels": {"stable": {"default": True}},
        "projects": {
            "pmu-demo": {"name": "pmu-demo", "path": "modules/pmu-demo"},
            "perf-demo": {"name": "perf-demo", "path": "modules/perf-demo"},
        },
        "modules": {
            "pmu-demo": {
                "project": "pmu-demo",
                "revision": "main",
                "metadata": str(pmu_root / "nsx-module.yaml"),
            },
            "perf-demo": {
                "project": "perf-demo",
                "revision": "main",
                "metadata": str(perf_root / "nsx-module.yaml"),
            },
        },
        "starter_profiles": {},
        "compat_matrix": {},
    }
    monkeypatch.setattr(module_discovery, "_load_registry", lambda: registry)

    cli.cmd_module_search(
        argparse.Namespace(
            query="profiling",
            app_dir=None,
            board=None,
            soc=None,
            toolchain=None,
            include_incompatible=False,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in payload["results"]] == ["perf-demo", "pmu-demo"] or [
        item["name"] for item in payload["results"]
    ] == ["pmu-demo", "perf-demo"]
    assert all(item["score"] > 0 for item in payload["results"])
    assert any(
        match["field"] in {"capabilities", "provides.features", "summary", "use_cases"}
        for match in payload["results"][0]["matches"]
    )


def test_cmd_module_search_filters_incompatible_results_by_target_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    compatible_root = tmp_path / "modules" / "pmu-demo"
    incompatible_root = tmp_path / "modules" / "uart-demo"
    compatible_root.mkdir(parents=True)
    incompatible_root.mkdir(parents=True)
    _write_searchable_module_metadata(
        compatible_root / "nsx-module.yaml",
        module_name="pmu-demo",
        capabilities=["profiling"],
        features=["profiling"],
        socs=["apollo510"],
    )
    _write_searchable_module_metadata(
        incompatible_root / "nsx-module.yaml",
        module_name="uart-demo",
        capabilities=["profiling"],
        features=["profiling"],
        socs=["apollo4p"],
    )
    registry = {
        "schema_version": 1,
        "channels": {"stable": {"default": True}},
        "projects": {
            "pmu-demo": {"name": "pmu-demo", "path": "modules/pmu-demo"},
            "uart-demo": {"name": "uart-demo", "path": "modules/uart-demo"},
        },
        "modules": {
            "pmu-demo": {
                "project": "pmu-demo",
                "revision": "main",
                "metadata": str(compatible_root / "nsx-module.yaml"),
            },
            "uart-demo": {
                "project": "uart-demo",
                "revision": "main",
                "metadata": str(incompatible_root / "nsx-module.yaml"),
            },
        },
        "starter_profiles": {},
        "compat_matrix": {},
    }
    monkeypatch.setattr(module_discovery, "_load_registry", lambda: registry)

    cli.cmd_module_search(
        argparse.Namespace(
            query="profiling",
            app_dir=None,
            board="apollo510_evb",
            soc="apollo510",
            toolchain="arm-none-eabi-gcc",
            include_incompatible=False,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    assert [item["name"] for item in payload["results"]] == ["pmu-demo"]
    assert payload["results"][0]["compatible"] is True


def test_module_search_parser_wiring() -> None:
    parser = cli._build_parser()
    args = parser.parse_args(["module", "search", "profiling", "--json", "--soc", "apollo510"])

    assert args.query == "profiling"
    assert args.json is True
    assert args.soc == "apollo510"
    assert args.func == cli.cmd_module_search


def test_validate_nsx_module_metadata_accepts_semantic_fields(tmp_path: Path) -> None:
    metadata_path = tmp_path / "semantic-module.yaml"
    _write_searchable_module_metadata(
        metadata_path,
        module_name="semantic-demo",
        summary="Helpful profiling support",
        capabilities=["profiling", "pmu"],
        use_cases=["function profiling"],
        features=["profiling"],
        socs=["apollo510"],
    )

    from neuralspotx.metadata import validate_nsx_module_metadata
    from neuralspotx.project_config import _read_yaml

    data = _read_yaml(metadata_path)
    validate_nsx_module_metadata(data, str(metadata_path))


def test_full_clean_removes_build_directory(tmp_path: Path) -> None:
    create_app(
        AppCreateRequest(app_dir=tmp_path / "hello_clean", board="apollo510_evb", no_bootstrap=True)
    )

    build_dir = tmp_path / "hello_clean" / "build" / "apollo510_evb"
    build_dir.mkdir(parents=True)
    (build_dir / "build.ninja").write_text("# fake\n", encoding="utf-8")

    clean_app(
        AppCleanRequest(
            app_dir=tmp_path / "hello_clean",
            full=True,
        )
    )

    assert not build_dir.exists()


def test_local_module_round_trip_add_update_remove(tmp_path: Path) -> None:
    create_app(
        AppCreateRequest(
            app_dir=tmp_path / "hello_modules", board="apollo510_evb", no_bootstrap=True
        )
    )

    app_dir = tmp_path / "hello_modules"
    project_root = tmp_path / "local-projects" / "local-demo"
    metadata_path = _write_local_module_project(project_root)

    register_module(
        ModuleRegisterRequest(
            app_dir=app_dir,
            module="local-demo",
            metadata=metadata_path,
            project="local-demo-proj",
            project_local_path=project_root,
        )
    )

    add_module(app_dir, "local-demo")

    cfg = _load_yaml(app_dir / "nsx.yml")
    assert [item["name"] for item in cfg["modules"]] == ["local-demo"]
    vendored_readme = app_dir / "modules" / "local-demo" / "README.md"
    assert vendored_readme.read_text(encoding="utf-8") == "version one\n"

    (project_root / "README.md").write_text("version two\n", encoding="utf-8")
    update_modules(app_dir, module="local-demo")
    assert vendored_readme.read_text(encoding="utf-8") == "version two\n"

    remove_module(app_dir, "local-demo")
    cfg = _load_yaml(app_dir / "nsx.yml")
    assert cfg["modules"] == []
    assert not (app_dir / "modules" / "local-demo").exists()


def test_build_app_uses_shared_impl_and_triggers_configure_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_app(
        AppCreateRequest(app_dir=tmp_path / "hello_build", board="apollo510_evb", no_bootstrap=True)
    )

    app_dir = tmp_path / "hello_build"
    build_dir = app_dir / "build" / "apollo510_evb"
    configure_calls: list[tuple[Path, Path, str, str | None]] = []
    build_calls: list[list[str]] = []

    def fake_configure(app: Path, build: Path, board: str, toolchain: str | None = None) -> None:
        configure_calls.append((app, build, board, toolchain))
        build.mkdir(parents=True, exist_ok=True)
        (build / "build.ninja").write_text("# fake\n", encoding="utf-8")

    def fake_run(cmd: list[str], cwd: Path | None = None) -> None:
        del cwd
        build_calls.append(cmd)

    monkeypatch.setattr(operations, "_run_cmake_configure", fake_configure)
    monkeypatch.setattr(operations, "_run", fake_run)

    build_app(AppBuildRequest(app_dir=app_dir, jobs=3))

    assert configure_calls == [(app_dir, build_dir, "apollo510_evb", None)]
    assert build_calls == [
        ["cmake", "--build", str(build_dir), "--target", "hello_build", "-j", "3"]
    ]
