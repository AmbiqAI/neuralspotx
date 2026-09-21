"""Prove the generated reference covers the whole public surface.

``test_public_surface_doc.py`` keeps the published symbol catalog in sync
with ``__all__``; this module covers the rendered pages behind it, and adds
the checks the generated pages make possible: that the argparse tree is
fully documented, that nothing private leaks into the output, and that the
configuration field tables still match the loaders.

The tests that need generated output skip when it is absent, because the
output is gitignored and only exists after ``npm run build:reference``.
CI runs the site build before pytest, so the skip never hides a gap there.
"""

from __future__ import annotations

import copy
import dataclasses
import importlib
import json
import re
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


# Named by public signatures but absent from ``__all__``, so nothing else in
# this file would notice them going missing. Spelled out rather than derived:
# recomputing them from the annotations would restate prune_griffe.py's own
# resolution, and a fourth one appearing is a decision, not an accident.
SUPPORTING_TYPES = {"BoardDescriptor", "EventKind", "PathLike"}


def test_supporting_types_are_documented(report: dict[str, Any]) -> None:
    """Types named by public signatures have to be reachable, not bare text.

    A reader meeting ``BoardDescriptor`` in a return type needs somewhere to
    click.
    """
    supporting = set(report["python"]["supporting"])
    assert supporting == SUPPORTING_TYPES, (
        "the documented supporting types changed: "
        f"missing {sorted(SUPPORTING_TYPES - supporting)}, "
        f"unexpected {sorted(supporting - SUPPORTING_TYPES)}"
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
        assert target is not None
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
#
# The field tables in scripts/docs/config_schema.yaml are hand-written, because
# only two of the four files are backed by a dataclass and neither of the other
# loaders is declarative. These tests are what stop the manifest being an
# unverified mirror: they check it against the loaders in both directions, so
# an invented field, a deleted field, a flipped required flag and a flipped
# type all fail.

SCHEMA_IDS = ["nsx-yml", "nsx-module-yaml", "board-yaml", "nsx-lock"]

# Dataclass attributes that describe where a document came from rather than
# anything inside it, so no documented field maps to them.
NON_FILE_FIELDS = {"path"}


def _resolve(dotted: str) -> Any:
    module_path, _, attribute = dotted.rpartition(".")
    return getattr(importlib.import_module(module_path), attribute)


def _schema(manifest: dict[str, Any], schema_id: str) -> dict[str, Any]:
    return next(item for item in manifest["schemas"] if item["id"] == schema_id)


def _leaf_paths(document: Any, prefix: str = "") -> list[str]:
    """Every dotted path in a document that names a scalar, list or empty map."""
    out: list[str] = []
    if isinstance(document, dict) and document:
        for key, value in document.items():
            out.extend(_leaf_paths(value, f"{prefix}{key}."))
        return out
    return [prefix.rstrip(".")] if prefix else []


def _get(document: Any, path: str) -> Any:
    cursor = document
    for part in path.split("."):
        if not isinstance(cursor, dict) or part not in cursor:
            return _MISSING
        cursor = cursor[part]
    return cursor


def _drop(document: dict[str, Any], path: str) -> dict[str, Any] | None:
    """Remove a dotted path from a copy, or return None if it is not there."""
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


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()


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


def _accepts(schema: dict[str, Any], document: dict[str, Any], tmp_path: Path) -> bool:
    """True when the loader takes the document as a usable one."""
    try:
        loaded = _load_document(schema, document, tmp_path)
    except Exception:
        return False
    if schema["id"] == "nsx-lock":
        # The lock is machine-written, so its reader answers with an empty
        # document rather than raising. Empty means unusable, which is the
        # rejection that matters here.
        return bool(getattr(loaded, "targets", None))
    return True


def _fixtures(schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Every coverage document for a schema.

    `coverage_example` is a multi-document YAML block, because some fields are
    only enforced in some shapes: a board.yaml that inherits takes its identity
    from its parent, so a second document covers the standalone case.
    """
    return [doc for doc in yaml.safe_load_all(schema["coverage_example"]) if doc]


def _enforced_paths(schema: dict[str, Any], tmp_path: Path) -> set[str]:
    """The paths the loader actually refuses to do without.

    Built by removing one path from a coverage fixture at a time, so it is the
    loader's own answer and not a restatement of the manifest. Both the leaves
    and the documented container paths are probed, because a whole missing
    section is exactly the kind of omission a loader rejects.
    """
    documented = _documented_paths(schema)
    enforced: set[str] = set()
    for coverage in _fixtures(schema):
        probes = set(_leaf_paths(coverage)) | {
            path for path in documented if _get(coverage, path) is not _MISSING
        }
        for path in probes:
            candidate = _drop(coverage, path)
            if candidate is None:
                continue
            if not _accepts(schema, candidate, tmp_path):
                enforced.add(path)
    return enforced


def _documented_paths(schema: dict[str, Any]) -> set[str]:
    """Documented paths that name a concrete key in a document.

    Paths with a `[]` or `<>` placeholder describe the shape of a repeated
    entry, which the coverage fixture exercises through its parent.
    """
    return {
        field["path"]
        for field in schema["fields"]
        if "[" not in field["path"] and "<" not in field["path"]
    }


TYPE_CHECKS = {
    "int": int,
    "bool": bool,
    "string": str,
    "map": dict,
}


def _type_matches(declared: str, value: Any) -> bool:
    if declared.startswith("list of") or declared.startswith("list "):
        return isinstance(value, list)
    if declared.startswith("map of"):
        return isinstance(value, dict)
    expected = TYPE_CHECKS.get(declared)
    if expected is None:
        return True
    if expected is int and isinstance(value, bool):
        return False
    if expected is str:
        # YAML gives a date or a number for some scalars a reader still reads
        # as text, so accept anything that is not a container.
        return not isinstance(value, (dict, list))
    return isinstance(value, expected)


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


@pytest.mark.parametrize("schema_id", SCHEMA_IDS)
def test_documented_example_is_accepted(
    manifest: dict[str, Any], schema_id: str, tmp_path: Path
) -> None:
    schema = _schema(manifest, schema_id)
    example = yaml.safe_load(schema["example"])
    assert _accepts(schema, example, tmp_path), (
        f"{schema['file']}: the example shown on the page is not accepted by {schema['loader']}"
    )


@pytest.mark.parametrize("schema_id", SCHEMA_IDS)
def test_coverage_fixture_is_accepted(
    manifest: dict[str, Any], schema_id: str, tmp_path: Path
) -> None:
    schema = _schema(manifest, schema_id)
    for index, coverage in enumerate(_fixtures(schema)):
        assert _accepts(schema, coverage, tmp_path), (
            f"{schema['file']}: coverage fixture {index} is not accepted by {schema['loader']}"
        )


@pytest.mark.parametrize("schema_id", SCHEMA_IDS)
def test_every_documented_field_exists_in_a_real_document(
    manifest: dict[str, Any], schema_id: str
) -> None:
    """A documented field the loader has never seen is an invention."""
    schema = _schema(manifest, schema_id)
    seen: set[str] = set()
    for coverage in _fixtures(schema):
        seen |= {path for path in _documented_paths(schema) if _get(coverage, path) is not _MISSING}
    missing = sorted(_documented_paths(schema) - seen)
    assert not missing, (
        f"{schema['file']} documents fields that the coverage fixture does not use, so "
        f"nothing proves the loader knows them: {missing}"
    )


@pytest.mark.parametrize("schema_id", SCHEMA_IDS)
def test_required_flags_match_the_loader(
    manifest: dict[str, Any], schema_id: str, tmp_path: Path
) -> None:
    """The required set in the manifest must equal the loader's own."""
    schema = _schema(manifest, schema_id)
    enforced = _enforced_paths(schema, tmp_path)
    documented_required = {
        field["path"]
        for field in schema["fields"]
        if field.get("required") and "[" not in field["path"] and "<" not in field["path"]
    }
    overstated = sorted(documented_required - enforced)
    understated = sorted(enforced - documented_required)
    assert not overstated, (
        f"{schema['file']} marks these required but {schema['loader']} accepts a document "
        f"without them: {overstated}"
    )
    assert not understated, (
        f"{schema['loader']} refuses a document without these, but {schema['file']} does "
        f"not mark them required: {understated}"
    )


@pytest.mark.parametrize("schema_id", SCHEMA_IDS)
def test_documented_types_match_the_fixture(manifest: dict[str, Any], schema_id: str) -> None:
    schema = _schema(manifest, schema_id)
    wrong = []
    for coverage in _fixtures(schema):
        for field in schema["fields"]:
            if "[" in field["path"] or "<" in field["path"]:
                continue
            value = _get(coverage, field["path"])
            if value is _MISSING:
                continue
            if not _type_matches(field["type"], value):
                wrong.append(
                    f"{field['path']} documented as {field['type']}, fixture has {value!r}"
                )
    assert not wrong, f"{schema['file']} type drift: {wrong}"


@pytest.mark.parametrize(
    ("schema_id", "model_dotted"),
    [
        ("board-yaml", "neuralspotx.board_descriptors.BoardDescriptor"),
        ("nsx-lock", "neuralspotx.nsx_lock.ResolvedModule"),
    ],
)
def test_dataclass_backed_field_sets_match(
    manifest: dict[str, Any], schema_id: str, model_dotted: str
) -> None:
    """Where a dataclass holds the parsed document, document every attribute.

    `model_field` carries the mapping because the file shape and the dataclass
    shape differ: board.yaml nests `board.name` onto `BoardDescriptor.name`,
    and the lock splits a module entry across two levels.
    """
    schema = _schema(manifest, schema_id)
    model = _resolve(model_dotted)
    attributes = {
        field.name for field in dataclasses.fields(model) if field.name not in NON_FILE_FIELDS
    }
    mapped = {
        field["model_field"].split(".", 1)[0]
        for field in schema["fields"]
        if field.get("model_field")
    }
    undocumented = sorted(attributes - mapped)
    invented = sorted(mapped - attributes)
    assert not undocumented, (
        f"{model_dotted} has fields that {schema['file']} does not document: {undocumented}"
    )
    assert not invented, (
        f"{schema['file']} maps fields onto {model_dotted} that do not exist: {invented}"
    )


def test_config_pages_cover_every_schema(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    documented = {schema["id"] for schema in report["config"]["schemas"]}
    expected = {schema["id"] for schema in manifest["schemas"]}
    assert documented == expected, (
        f"configuration pages differ from the manifest: {documented ^ expected}"
    )
    for schema in report["config"]["schemas"]:
        assert schema["fields"] > 0, f"{schema['file']} rendered with no fields"


# --- Hand-written notes ----------------------------------------------------


def test_every_notes_paragraph_reaches_its_page() -> None:
    """The merge step is silent when it drops prose, so check it did not.

    Compares text rather than markup: the generator rewrites links onto the new
    routes, and MDX comments never reach the reader.
    """
    notes_dir = SITE / "reference-notes" / "cli"
    pages_dir = CLI_PAGES
    if not pages_dir.exists():
        pytest.skip("CLI pages are absent; run npm run build:reference")

    def plain(text: str) -> str:
        text = re.sub(r"\{/\*.*?\*/\}", " ", text, flags=re.S)
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = text.replace("`", "")
        return re.sub(r"\s+", " ", text).strip()

    notes_files = sorted(notes_dir.glob("*.md"))
    assert notes_files, "no hand-written notes found"
    for note in notes_files:
        page = pages_dir / f"{note.stem}.mdx"
        assert page.exists(), f"notes exist for {note.stem} but no page was generated"
        rendered = plain(page.read_text(encoding="utf-8"))
        for paragraph in note.read_text(encoding="utf-8").split("\n\n"):
            text = plain(paragraph)
            if len(text) < 25:
                continue
            assert text in rendered, (
                f"{note.name}: this paragraph did not reach the generated page: {text[:90]}..."
            )


def test_app_scoped_commands_keep_their_selector_prose() -> None:
    """These five share the app-selector and SDK prose, and it was lost once."""
    if not CLI_PAGES.exists():
        pytest.skip("CLI pages are absent; run npm run build:reference")

    def flat(slug: str) -> str:
        # The pages are hard-wrapped, so a phrase can straddle a line break.
        return re.sub(r"\s+", " ", (CLI_PAGES / f"{slug}.mdx").read_text(encoding="utf-8")).lower()

    for slug in ("build", "clean", "configure", "flash", "view"):
        page = flat(slug)
        assert "searches upward" in page, f"nsx {slug} lost the --app-dir upward search"
        assert "examples/" in page, f"nsx {slug} lost how the positional app is resolved"
    for slug in ("build", "configure", "flash", "view"):
        assert "sdk provider selection" in flat(slug), f"nsx {slug} lost the --sdk-root pointer"
