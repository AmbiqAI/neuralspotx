"""Keep ``neuralspotx.__all__`` and the published symbol catalog in sync.

``astro-site/public/reference/python-symbols.json`` is what the site serves to
agents and what ``check-discoverability-output.mjs`` asserts the llms bundle
covers. That Node check cannot import the package, so it trusts the catalog to
be the public surface; this module is what makes that true.

The catalog is generated and gitignored, so the test skips when it is absent.
CI runs ``npm run build:reference`` before pytest, so the skip never hides a
gap there.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import neuralspotx

CATALOG_PATH = (
    Path(__file__).resolve().parents[1]
    / "astro-site"
    / "public"
    / "reference"
    / "python-symbols.json"
)


@pytest.fixture(scope="module")
def catalog() -> dict:
    if not CATALOG_PATH.exists():
        pytest.skip(f"{CATALOG_PATH.name} is absent; run npm run build:reference")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_published_catalog_matches_all(catalog: dict) -> None:
    declared = set(neuralspotx.__all__)
    published = {symbol["name"] for symbol in catalog["symbols"]}
    missing = declared - published
    extra = published - declared
    assert not missing, (
        f"names in neuralspotx.__all__ but absent from {CATALOG_PATH.name}: {sorted(missing)}"
    )
    assert not extra, (
        f"names published in {CATALOG_PATH.name} but absent from neuralspotx.__all__: "
        f"{sorted(extra)}"
    )


def test_published_paths_import_from_the_package(catalog: dict) -> None:
    """Each entry's ``path`` must be the module the name really lives in."""

    for symbol in catalog["symbols"]:
        assert symbol["path"] == f"{symbol['module']}.{symbol['name']}", (
            f"{symbol['name']}: path {symbol['path']!r} does not match module {symbol['module']!r}"
        )
        assert symbol["module"].startswith("neuralspotx"), (
            f"{symbol['name']} is published under {symbol['module']!r}, outside the package"
        )


def test_every_public_name_is_importable() -> None:
    for name in neuralspotx.__all__:
        assert hasattr(neuralspotx, name), (
            f"neuralspotx.__all__ lists {name!r} but it is not importable"
        )
