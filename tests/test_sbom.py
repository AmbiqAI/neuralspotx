"""Phase 5 — SBOM generation tests.

Validates ``api.generate_sbom`` and the ``nsx sbom`` CLI for both SPDX 2.3
JSON (default) and CycloneDX 1.5 JSON output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from neuralspotx import NSXConfigError, generate_sbom
from neuralspotx.nsx_lock import LockKind, NsxLock, ResolvedModule, hash_tree, write_lock


def _write_nsx_yml(app_dir: Path, modules: list[dict[str, Any]]) -> None:
    cfg = {
        "schema_version": 2,
        "project": {"name": "testapp"},
        "target": {"board": "apollo510_evb", "soc": "apollo510"},
        "toolchain": "arm-none-eabi-gcc",
        "modules": modules,
    }
    (app_dir / "nsx.yml").write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")


def _make_vendored(app_dir: Path, name: str, content: str = "hello") -> None:
    mod = app_dir / "modules" / name
    mod.mkdir(parents=True, exist_ok=True)
    (mod / "src.c").write_text(content, encoding="utf-8")


@pytest.fixture
def app_with_lock(tmp_path: Path) -> Path:
    _make_vendored(tmp_path, "alpha", "a")
    _make_vendored(tmp_path, "beta", "b")
    _write_nsx_yml(
        tmp_path,
        [
            {"name": "alpha", "source": {"vendored": True}},
            {"name": "beta", "source": {"vendored": True}},
        ],
    )
    write_lock(
        tmp_path,
        NsxLock(
            target={"board": "apollo510_evb"},
            modules={
                name: ResolvedModule(
                    project=name,
                    kind=LockKind.VENDORED,
                    constraint="",
                    vendored_at=f"modules/{name}",
                    content_hash=hash_tree(tmp_path / "modules" / name),
                    acquired_at="2026-07-28T00:00:00Z",
                )
                for name in ("alpha", "beta")
            },
        ),
    )
    return tmp_path


@pytest.mark.parametrize(
    ("with_app_config", "kind", "duplicate"),
    [
        (True, LockKind.GIT, False),
        (False, LockKind.GIT, False),
        (False, LockKind.UNRESOLVED, False),
        (True, LockKind.GIT, True),
    ],
)
def test_license_scopes_follow_locked_monorepo_sources(
    tmp_path: Path, with_app_config: bool, kind: LockKind, duplicate: bool
) -> None:
    name = "custom-rtos"
    root = tmp_path / "modules" / "nsx-ambiq-sdk"
    module_dir = root / "modules" / name
    module_dir.mkdir(parents=True)
    manifest = module_dir / "nsx-module.yaml"
    manifest.write_text(
        "schema_version: 1\nmodule: {name: custom-rtos}\n"
        "licenses: {'.': BSD-3-Clause, kernel: MIT, legacy.c: null}\n",
        encoding="utf-8",
    )
    if duplicate:
        alternate = root / "alternate" / "nsx-module.yaml"
        alternate.parent.mkdir()
        alternate.write_text(
            manifest.read_text(encoding="utf-8").replace("MIT", "ISC"), encoding="utf-8"
        )
    if with_app_config:
        _write_nsx_yml(tmp_path, [])
    write_lock(
        tmp_path,
        NsxLock(
            target={"board": "apollo510_evb"},
            modules={
                name: ResolvedModule(
                    project="nsx-ambiq-sdk",
                    kind=kind,
                    vendored_at="modules/nsx-ambiq-sdk",
                    content_hash=hash_tree(root),
                    manifest_path=manifest.relative_to(root).as_posix(),
                    constraint="v5.2.30",
                    acquired_at="2026-07-28T00:00:00Z",
                ),
            },
        ),
    )

    spdx = json.loads(generate_sbom(tmp_path))["packages"][1]
    cdx = json.loads(generate_sbom(tmp_path, format="cyclonedx"))["components"][0]
    assert spdx["licenseDeclared"] == "NOASSERTION"
    assert spdx["licenseComments"].splitlines() == [
        "modules/custom-rtos: BSD-3-Clause",
        "modules/custom-rtos/kernel: MIT",
        "modules/custom-rtos/legacy.c: NOASSERTION",
    ]
    assert {
        key: value
        for key, value in _cyclonedx_properties(cdx).items()
        if key.startswith("nsx:license:")
    } == {
        "nsx:license:modules/custom-rtos": "BSD-3-Clause",
        "nsx:license:modules/custom-rtos/kernel": "MIT",
        "nsx:license:modules/custom-rtos/legacy.c": "NOASSERTION",
    }
    assert "licenses" not in cdx

    # A source edit with an unchanged lock must not change its declared terms.
    manifest.write_text(
        "schema_version: 1\nmodule: {name: custom-rtos}\nlicenses: {'.': MIT}\n",
        encoding="utf-8",
    )
    spdx = json.loads(generate_sbom(tmp_path))["packages"][1]
    cdx = json.loads(generate_sbom(tmp_path, format="cyclonedx"))["components"][0]
    assert "licenseComments" not in spdx
    assert not any(key.startswith("nsx:license:") for key in _cyclonedx_properties(cdx))


class TestGenerateSbomSpdx:
    def test_default_format_is_spdx_and_returns_valid_json(self, app_with_lock: Path) -> None:
        out = generate_sbom(app_with_lock)
        doc = json.loads(out)
        assert doc["spdxVersion"] == "SPDX-2.3"
        assert doc["dataLicense"] == "CC0-1.0"
        assert doc["SPDXID"] == "SPDXRef-DOCUMENT"
        assert doc["documentNamespace"].startswith("https://")
        assert "creationInfo" in doc
        assert isinstance(doc["packages"], list)
        assert isinstance(doc["relationships"], list)

    def test_packages_include_root_app_and_every_module(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock, format="spdx"))
        names = {pkg["name"] for pkg in doc["packages"]}
        assert "alpha" in names
        assert "beta" in names
        # Root app package present.
        assert any(pkg["SPDXID"] == "SPDXRef-Package-App" for pkg in doc["packages"])

    def test_module_packages_carry_sha256_checksum(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock))
        alpha = next(p for p in doc["packages"] if p["name"] == "alpha")
        assert "checksums" in alpha
        sha = next(c for c in alpha["checksums"] if c["algorithm"] == "SHA256")
        # 64 hex chars
        assert len(sha["checksumValue"]) == 64

    def test_describes_relationship_to_root(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock))
        describes = [r for r in doc["relationships"] if r["relationshipType"] == "DESCRIBES"]
        assert len(describes) == 1
        assert describes[0]["spdxElementId"] == "SPDXRef-DOCUMENT"

    def test_each_module_has_depends_on_relationship(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock))
        depends = [r for r in doc["relationships"] if r["relationshipType"] == "DEPENDS_ON"]
        # one per module (alpha + beta)
        assert len(depends) >= 2


class TestGenerateSbomCycloneDx:
    def test_cyclonedx_format_is_valid_json(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock, format="cyclonedx"))
        assert doc["bomFormat"] == "CycloneDX"
        assert doc["specVersion"] == "1.5"
        assert doc["serialNumber"].startswith("urn:uuid:")
        assert isinstance(doc["components"], list)

    def test_components_include_every_module(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock, format="cyclonedx"))
        names = {c["name"] for c in doc["components"]}
        assert "alpha" in names
        assert "beta" in names

    def test_components_carry_sha256_hash(self, app_with_lock: Path) -> None:
        doc = json.loads(generate_sbom(app_with_lock, format="cyclonedx"))
        alpha = next(c for c in doc["components"] if c["name"] == "alpha")
        assert "hashes" in alpha
        assert any(h["alg"] == "SHA-256" for h in alpha["hashes"])

    def test_serial_number_is_rfc4122_uuid(self, app_with_lock: Path) -> None:
        import uuid as _uuid

        doc = json.loads(generate_sbom(app_with_lock, format="cyclonedx"))
        urn = doc["serialNumber"]
        assert urn.startswith("urn:uuid:")
        # Must round-trip through uuid.UUID — sliced sha-256 hex would not.
        parsed = _uuid.UUID(urn[len("urn:uuid:") :])
        assert parsed.version == 5


def _write_git_provenance_lock(app_dir: Path) -> None:
    _write_nsx_yml(app_dir, [])
    write_lock(
        app_dir,
        NsxLock(
            generated_at="2026-07-28T00:00:00Z",
            nsx_tool_version="0.7.8",
            target={
                "board": "apollo510_evb",
                "soc": "apollo510",
                "toolchain": "arm-none-eabi-gcc",
            },
            modules={
                "sdk-tagged": ResolvedModule(
                    project="sdk",
                    kind=LockKind.GIT,
                    constraint="v5.2.23",
                    vendored_at="modules/sdk",
                    content_hash="sha256:" + "a" * 64,
                    acquired_at="2026-07-28T00:00:00Z",
                    url="https://example.com/sdk.git",
                    tag="v5.2.23",
                    commit="1" * 40,
                ),
                "sdk-bringup": ResolvedModule(
                    project="sdk",
                    kind=LockKind.GIT,
                    constraint="bringup/customer-board",
                    vendored_at="modules/sdk-bringup",
                    content_hash="sha256:" + "b" * 64,
                    acquired_at="2026-07-28T00:00:00Z",
                    url="https://example.com/sdk.git",
                    commit="2" * 40,
                ),
            },
        ),
    )


def _spdx_comment_fields(package: dict[str, Any]) -> dict[str, str]:
    return dict(field.split("=", 1) for field in package["comment"].split("; "))


def _cyclonedx_properties(component: dict[str, Any]) -> dict[str, str]:
    return {item["name"]: item["value"] for item in component["properties"]}


class TestSbomGitProvenance:
    def test_spdx_includes_requested_refs_commits_and_tool_version(self, tmp_path: Path) -> None:
        _write_git_provenance_lock(tmp_path)

        document = json.loads(generate_sbom(tmp_path, format="spdx"))
        packages = {package["name"]: package for package in document["packages"]}
        tagged = packages["sdk-tagged"]
        bringup = packages["sdk-bringup"]

        assert document["creationInfo"]["creators"] == ["Tool: neuralspotx 0.7.8"]
        assert tagged["versionInfo"] == "1" * 40
        assert tagged["downloadLocation"].endswith("@" + "1" * 40)
        assert _spdx_comment_fields(tagged)["constraint"] == "v5.2.23"
        assert _spdx_comment_fields(tagged)["tag"] == "v5.2.23"
        assert bringup["versionInfo"] == "2" * 40
        assert _spdx_comment_fields(bringup)["constraint"] == "bringup/customer-board"
        assert "tag" not in _spdx_comment_fields(bringup)

    def test_cyclonedx_includes_requested_refs_commits_and_tool_version(
        self,
        tmp_path: Path,
    ) -> None:
        _write_git_provenance_lock(tmp_path)

        document = json.loads(generate_sbom(tmp_path, format="cyclonedx"))
        components = {component["name"]: component for component in document["components"]}
        tagged = components["sdk-tagged"]
        bringup = components["sdk-bringup"]

        assert document["metadata"]["tools"] == [
            {"vendor": "AmbiqAI", "name": "neuralspotx", "version": "0.7.8"}
        ]
        assert tagged["version"] == "1" * 40
        assert _cyclonedx_properties(tagged)["nsx:constraint"] == "v5.2.23"
        assert _cyclonedx_properties(tagged)["nsx:tag"] == "v5.2.23"
        assert bringup["version"] == "2" * 40
        assert _cyclonedx_properties(bringup)["nsx:constraint"] == "bringup/customer-board"
        assert "nsx:tag" not in _cyclonedx_properties(bringup)


class TestGenerateSbomErrors:
    def test_missing_lock_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NSXConfigError) as exc:
            generate_sbom(tmp_path)
        assert "nsx.lock" in str(exc.value)

    def test_unsupported_format_raises(self, app_with_lock: Path) -> None:
        with pytest.raises(NSXConfigError) as exc:
            generate_sbom(app_with_lock, format="xml")
        assert "format" in str(exc.value).lower()


class TestSbomCli:
    def test_cli_writes_to_stdout_by_default(
        self, app_with_lock: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from neuralspotx import cli

        rc = cli.main(["sbom", "--app-dir", str(app_with_lock)])
        assert rc == 0
        out = capsys.readouterr().out
        doc = json.loads(out)
        assert doc["spdxVersion"] == "SPDX-2.3"

    def test_cli_writes_to_output_file(
        self, app_with_lock: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from neuralspotx import cli

        out_path = tmp_path / "bom.json"
        rc = cli.main([
            "sbom",
            "--app-dir",
            str(app_with_lock),
            "--format",
            "cyclonedx",
            "--output",
            str(out_path),
        ])
        assert rc == 0
        assert out_path.exists()
        doc = json.loads(out_path.read_text(encoding="utf-8"))
        assert doc["bomFormat"] == "CycloneDX"


class TestSpdxDownloadLocationGitPrefix:
    """SPDX downloadLocation must not double-prefix ``git+``."""

    def _build(self, url: str) -> str:
        from neuralspotx.operations._sbom import _build_spdx_document

        lock = NsxLock(
            modules={
                "mod": ResolvedModule(
                    project="proj",
                    kind=LockKind.GIT,
                    constraint="main",
                    vendored_at="modules/mod",
                    content_hash="sha256:" + "a" * 64,
                    acquired_at="2025-01-01T00:00:00Z",
                    url=url,
                    commit="deadbeef" * 5,
                )
            }
        )
        doc = _build_spdx_document(Path("/tmp/app"), lock, "apollo510_evb")
        pkg = next(p for p in doc["packages"] if p["name"] == "mod")
        return pkg["downloadLocation"]

    def test_plain_https_gets_git_prefix(self) -> None:
        loc = self._build("https://example.com/foo.git")
        assert loc.startswith("git+https://")
        assert not loc.startswith("git+git+")

    def test_url_already_prefixed_is_not_double_prefixed(self) -> None:
        loc = self._build("git+https://example.com/foo.git")
        assert loc.startswith("git+https://")
        assert not loc.startswith("git+git+")


@pytest.fixture
def two_board_lock(app_with_lock: Path) -> Path:
    from dataclasses import replace

    from neuralspotx.nsx_lock import read_lock

    app = app_with_lock
    default = "apollo510_evb"
    custom = "MyBoard"
    (app / "nsx.yml").write_text(
        yaml.safe_dump({
            "schema_version": 2,
            "project": {"name": "demo"},
            "targets": {"default": default, "supported": [default, custom]},
            "baseline": "none",
            "modules": [],
        })
    )
    original = read_lock(app, default)
    assert original is not None
    root = app / "modules/shared"
    root.mkdir()
    (root / "nsx-module.yaml").write_text(
        "schema_version: 1\nmodule: {name: shared}\nlicenses: {'.': MIT}\n"
    )
    shared = replace(
        original.modules["alpha"],
        project="shared",
        kind=LockKind.GIT,
        url="https://example.invalid/shared.git",
        vendored_at="modules/shared",
        manifest_path="nsx-module.yaml",
        commit="a" * 40,
        content_hash=hash_tree(root),
    )
    for board, only, entry in [
        (default, "alpha", shared),
        (custom, "beta", replace(shared, commit="b" * 40, content_hash="sha256:" + "b" * 64)),
    ]:
        # The outer section key identifies the board even for a minimal receipt.
        write_lock(app, NsxLock(modules={only: original.modules[only], "shared": entry}), board)
    return app


@pytest.mark.parametrize("fmt", ["spdx", "cyclonedx"])
def test_sbom_selects_one_locked_board(
    two_board_lock: Path,
    fmt: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from neuralspotx import cli

    app = two_board_lock
    monkeypatch.setattr("neuralspotx.operations._sbom._utc_now", lambda: "2026-11-26T00:00:00Z")
    before = {p: p.read_bytes() for p in app.rglob("*") if p.is_file()}
    documents = []
    for board, only, rev in [("apollo510_evb", "alpha", "a" * 40), ("MyBoard", "beta", "b" * 40)]:
        doc = json.loads(generate_sbom(app, board=board, format=fmt))
        documents.append(doc)
        assert cli.main(["sbom", "--app-dir", str(app), "--board", board, "--format", fmt]) == 0
        assert json.loads(capsys.readouterr().out) == doc
        if fmt == "spdx":
            assert doc["comment"] == f"nsx:board={board}"
            packages = {p["name"]: p for p in doc["packages"]}
            assert set(packages) == {app.name, only, "shared"}
            shared = packages["shared"]
            assert shared["versionInfo"] == rev
            assert ("licenseComments" in shared) == (only == "alpha")
            digest = shared["checksums"][0]["checksumValue"]
        else:
            assert _cyclonedx_properties(doc["metadata"])["nsx:board"] == board
            components = {c["name"]: c for c in doc["components"]}
            assert set(components) == {only, "shared"}
            shared = components["shared"]
            assert shared["version"] == rev
            assert ("nsx:license:." in _cyclonedx_properties(shared)) == (only == "alpha")
            digest = shared["hashes"][0]["content"]
        expected = (
            hash_tree(app / "modules/shared").removeprefix("sha256:")
            if only == "alpha"
            else "b" * 64
        )
        assert digest == expected
    identity = "documentNamespace" if fmt == "spdx" else "serialNumber"
    assert documents[0][identity] != documents[1][identity]
    assert json.loads(generate_sbom(app, format=fmt)) == documents[0]
    assert {p: p.read_bytes() for p in app.rglob("*") if p.is_file()} == before


def test_sbom_lock_only_selection_and_errors(
    two_board_lock: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from neuralspotx import cli

    app = two_board_lock
    config = app / "nsx.yml"
    config.unlink()
    assert (
        json.loads(generate_sbom(app, board="APOLLO510_EVB"))["comment"]
        == "nsx:board=apollo510_evb"
    )
    with pytest.raises(NSXConfigError, match="--board.*MyBoard.*apollo510_evb"):
        generate_sbom(app)
    output = app / "report.json"
    output.write_bytes(b"existing")
    assert (
        cli.main(["sbom", "--app-dir", str(app), "--board", "other", "--output", str(output)]) == 1
    )
    assert "other" in capsys.readouterr().err and output.read_bytes() == b"existing"

    path = app / "nsx.lock"
    receipt = yaml.safe_load(path.read_text())
    del receipt["targets"]["apollo510_evb"]
    path.write_text(yaml.safe_dump(receipt))
    assert json.loads(generate_sbom(app))["comment"] == "nsx:board=MyBoard"
    with pytest.raises(NSXConfigError, match="apollo510_evb.*missing"):
        generate_sbom(app, board="apollo510_evb")
    config.write_bytes(b"\xff")
    assert json.loads(generate_sbom(app))["comment"] == "nsx:board=MyBoard"
    _write_nsx_yml(app, [])
    with pytest.raises(NSXConfigError, match="apollo510_evb.*missing"):
        generate_sbom(app)


@pytest.mark.parametrize("subdir", [".", "reports"])
def test_sbom_cli_prefers_nearest_archived_receipt(
    app_with_lock: Path,
    subdir: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from neuralspotx import cli, find_app_root

    archive = app_with_lock / "archive"
    cwd = archive / subdir
    cwd.mkdir(parents=True)
    write_lock(archive, NsxLock(), board="apollo510_evb")
    monkeypatch.chdir(cwd)
    assert find_app_root() == app_with_lock
    assert cli.main(["sbom", "--board", "apollo510_evb", "--format", "cyclonedx"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["metadata"]["component"]["name"] == "archive" and doc["components"] == []
