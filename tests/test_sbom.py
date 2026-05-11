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
from neuralspotx.operations import lock_app_impl


def _write_nsx_yml(app_dir: Path, modules: list[dict[str, Any]]) -> None:
    cfg = {
        "schema_version": 1,
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
    lock_app_impl(tmp_path)
    return tmp_path


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


class TestGenerateSbomErrors:
    def test_missing_lock_raises(self, tmp_path: Path) -> None:
        with pytest.raises(NSXConfigError) as exc:
            generate_sbom(tmp_path)
        assert "nsx.lock" in str(exc.value)

    def test_unsupported_format_raises(self, app_with_lock: Path) -> None:
        with pytest.raises(NSXConfigError) as exc:
            generate_sbom(app_with_lock, format="xml")  # type: ignore[arg-type]
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
        from neuralspotx.nsx_lock import LockKind, NsxLock, ResolvedModule
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
        doc = _build_spdx_document(Path("/tmp/app"), lock)
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
