"""Prove the generated reference covers the whole public surface.

``test_public_surface_doc.py`` keeps the MkDocs page in sync with
``__all__``; this module does the same job for the generated Astro
reference, and adds the checks the generated pages make possible: that the
argparse tree is fully documented, that nothing private leaks into the
output, and that the configuration field tables still match the loaders.

The tests that need generated output skip when it is absent, because the
output is gitignored and only exists after ``npm run build:reference``.
CI runs the site build before pytest, so the skip never hides a gap there.
"""

from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import neuralspotx

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts" / "docs"
SITE = REPO_ROOT / "astro-site"
REPORT_PATH = SITE / "src" / "data" / "reference-report.json"
CLI_PAGES = SITE / "src" / "content" / "docs" / "reference" / "cli"
API_PAGES = SITE / "src" / "content" / "docs" / "reference" / "api"
CONFIG_MANIFEST = SCRIPTS / "config_schema.yaml"

pytest.importorskip("yaml")


def _load_script(name: str):
    """Import a scripts/docs module without making scripts/ a package."""
    import sys

    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    return importlib.import_module(name)


@pytest.fixture(scope="module")
def cli_tree() -> dict[str, Any]:
    return _load_script("dump_cli").build()


@pytest.fixture(scope="module")
def report() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        pytest.skip(f"{REPORT_PATH.relative_to(REPO_ROOT)} is absent; run npm run build:reference")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return yaml.safe_load(CONFIG_MANIFEST.read_text(encoding="utf-8"))


# --- Python API ------------------------------------------------------------


def test_every_public_name_has_a_generated_anchor(report: dict[str, Any]) -> None:
    anchored = {symbol["name"] for symbol in report["python"]["symbols"]}
    missing = set(neuralspotx.__all__) - anchored
    extra = anchored - set(neuralspotx.__all__)
    assert not missing, f"names in neuralspotx.__all__ with no generated anchor: {sorted(missing)}"
    assert not extra, f"generated anchors for names outside neuralspotx.__all__: {sorted(extra)}"


def test_anchors_are_importable_paths(report: dict[str, Any]) -> None:
    """An anchor doubles as the import path, so it has to resolve."""
    for symbol in report["python"]["symbols"]:
        module_path, _, name = symbol["anchor"].rpartition(".")
        module = importlib.import_module(module_path)
        assert hasattr(module, name), f"anchor {symbol['anchor']} does not resolve"
        assert getattr(module, name) is getattr(neuralspotx, symbol["name"]), (
            f"{symbol['anchor']} is not the same object as neuralspotx.{symbol['name']}"
        )


def test_no_private_module_is_documented(report: dict[str, Any]) -> None:
    for symbol in report["python"]["symbols"]:
        segments = symbol["anchor"].split(".")[1:-1] + symbol["route"].split("/")
        private = [segment for segment in segments if segment.startswith("_")]
        assert not private, f"{symbol['anchor']} is documented under a private path: {private}"

    if API_PAGES.exists():
        for page in API_PAGES.rglob("*.mdx"):
            relative = page.relative_to(API_PAGES)
            private = [part for part in relative.parts if part.startswith("_")]
            assert not private, f"generated a page for a private path: {relative}"


def test_no_unresolved_cross_references(report: dict[str, Any]) -> None:
    assert report["unresolvedReferences"] == 0, (
        f"the generator reported {report['unresolvedReferences']} unresolved cross-references"
    )


def test_every_symbol_has_a_category(report: dict[str, Any]) -> None:
    allowed = {"errors", "models", "functions", "emitters"}
    for symbol in report["python"]["symbols"]:
        assert symbol["category"] in allowed, (
            f"{symbol['name']} has category {symbol['category']!r}, expected one of {sorted(allowed)}"
        )


# --- CLI -------------------------------------------------------------------


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for node in nodes:
        out.append(node)
        out.extend(_walk(node.get("subcommands") or []))
    return out


def test_dump_covers_the_whole_parser(cli_tree: dict[str, Any]) -> None:
    nodes = _walk(cli_tree["commands"])
    assert len(cli_tree["commands"]) == 21, "the top-level parser count changed"
    assert len(cli_tree["aliases"]) == 3
    distinct = [node for node in cli_tree["commands"] if not node["alias_of"]]
    assert len(distinct) == 18, f"expected 18 distinct commands, got {len(distinct)}"
    for node in nodes:
        assert node["usage"], f"nsx {node['name']} has no usage line"
        assert node["slug"], f"nsx {node['name']} has no slug"


def test_every_alias_dispatches_to_its_target(cli_tree: dict[str, Any]) -> None:
    """The aliases are sibling parsers, so only the handler proves the link."""
    dump_cli = _load_script("dump_cli")
    parser = dump_cli._build_parser()
    action = dump_cli._subparsers_action(parser)
    assert action is not None

    def handler(name: str):
        current = action
        target = None
        for part in name.split(" "):
            target = current.choices[part]
            current = dump_cli._subparsers_action(target) or current
        return target.get_default("func")

    for alias, command in cli_tree["aliases"].items():
        assert handler(alias) is handler(command), (
            f"nsx {alias} no longer dispatches to the same handler as nsx {command}"
        )


def test_every_command_and_subcommand_has_a_page(
    cli_tree: dict[str, Any], report: dict[str, Any]
) -> None:
    documented = {command["name"] for command in report["cli"]["commands"]}
    expected = {node["name"] for node in _walk(cli_tree["commands"])}
    missing = expected - documented
    extra = documented - expected
    assert not missing, f"CLI commands with no generated page: {sorted(missing)}"
    assert not extra, f"generated pages for commands the parser does not register: {sorted(extra)}"

    if CLI_PAGES.exists():
        for node in _walk(cli_tree["commands"]):
            page = CLI_PAGES / f"{node['slug']}.mdx"
            assert page.exists(), f"missing page {page.relative_to(SITE)} for nsx {node['name']}"


def test_every_option_reaches_the_page(cli_tree: dict[str, Any]) -> None:
    if not CLI_PAGES.exists():
        pytest.skip("CLI pages are absent; run npm run build:reference")
    for node in _walk(cli_tree["commands"]):
        text = (CLI_PAGES / f"{node['slug']}.mdx").read_text(encoding="utf-8")
        for argument in node["arguments"]:
            token = argument["flags"][-1] if argument["flags"] else argument["name"]
            assert token in text, f"nsx {node['name']} page does not mention {token}"


# --- Configuration ---------------------------------------------------------


def _resolve(dotted: str) -> Any:
    module_path, _, attribute = dotted.rpartition(".")
    return getattr(importlib.import_module(module_path), attribute)


def _drop(document: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Remove a dotted field from a copy, or return None if it is not there."""
    clone = copy.deepcopy(document)
    cursor: Any = clone
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(cursor, dict) or part not in cursor:
            return None
        cursor = cursor[part]
    if not isinstance(cursor, dict) or parts[-1] not in cursor:
        return None
    del cursor[parts[-1]]
    return clone


def _load_document(schema: dict[str, Any], document: dict[str, Any], tmp_path: Path) -> Any:
    """Push a document through the loader the manifest names."""
    loader = _resolve(schema["loader"])
    if schema["id"] == "nsx-module-yaml":
        return loader(document, "test-module")
    target = tmp_path / schema["file"]
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    if schema["id"] == "nsx-lock":
        return loader(tmp_path)
    return loader(target)


def _validate(schema: dict[str, Any], document: dict[str, Any], tmp_path: Path) -> None:
    loaded = _load_document(schema, document, tmp_path)
    if schema["id"] == "nsx-lock":
        assert loaded is not None and getattr(loaded, "targets", None), (
            f"{schema['file']}: the documented example did not load as a usable lock"
        )


def test_manifest_schema_versions_match_the_code(manifest: dict[str, Any]) -> None:
    for schema in manifest["schemas"]:
        constant = schema.get("schema_version_constant")
        if not constant:
            continue
        assert _resolve(constant) == schema["schema_version"], (
            f"{schema['file']} documents schema_version {schema['schema_version']} "
            f"but {constant} is {_resolve(constant)}"
        )


def test_manifest_entry_points_exist(manifest: dict[str, Any]) -> None:
    for schema in manifest["schemas"]:
        assert callable(_resolve(schema["loader"])), f"{schema['loader']} is not callable"
        if schema.get("model"):
            _resolve(schema["model"])


@pytest.mark.parametrize("schema_id", ["nsx-yml", "nsx-module-yaml", "board-yaml", "nsx-lock"])
def test_documented_example_is_accepted(
    manifest: dict[str, Any], schema_id: str, tmp_path: Path
) -> None:
    schema = next(item for item in manifest["schemas"] if item["id"] == schema_id)
    _validate(schema, yaml.safe_load(schema["example"]), tmp_path)


@pytest.mark.parametrize("schema_id", ["nsx-yml", "nsx-module-yaml", "board-yaml", "nsx-lock"])
def test_required_fields_are_really_required(
    manifest: dict[str, Any], schema_id: str, tmp_path: Path
) -> None:
    """Drop one documented required field at a time and check what happens.

    A field the manifest calls required but the loader shrugs at is drift, and
    so is a field the loader now requires that the example does not carry,
    which the previous test catches. NSX writes the lock rather than reading
    someone's, so its reader regenerates instead of rejecting; the manifest
    says which behavior a schema has and this asserts that one.
    """
    schema = next(item for item in manifest["schemas"] if item["id"] == schema_id)
    behavior = schema.get("missing_required_behavior", "reject")
    example = yaml.safe_load(schema["example"])
    checked = 0
    for field in schema["fields"]:
        if not field.get("required"):
            continue
        # Only fields the example actually carries can be removed from it;
        # the ones under a map key placeholder are covered by their parent.
        if "[" in field["path"] or "<" in field["path"]:
            continue
        candidate = _drop(example, field["path"])
        if candidate is None:
            continue
        checked += 1
        if behavior == "reject":
            with pytest.raises(Exception, match=r".*"):
                _validate(schema, candidate, tmp_path)
        else:
            loaded = _load_document(schema, candidate, tmp_path)
            assert not getattr(loaded, "targets", None), (
                f"{schema['file']} without {field['path']} still loaded as a usable document; "
                "the reader is meant to treat it as absent and regenerate it"
            )
    assert checked, f"{schema['file']}: the example exercises no documented required field"


def test_config_pages_cover_every_schema(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    documented = {schema["id"] for schema in report["config"]["schemas"]}
    expected = {schema["id"] for schema in manifest["schemas"]}
    assert documented == expected, (
        f"configuration pages differ from the manifest: {documented ^ expected}"
    )
    for schema in report["config"]["schemas"]:
        assert schema["fields"] > 0, f"{schema['file']} rendered with no fields"
