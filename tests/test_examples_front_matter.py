"""Contract for the front matter each ``examples/<name>/README.md`` declares.

The README is the single source for both the example's prose and the row it
gets in the site's Examples table, which ``astro-site/scripts/build-examples.mjs``
renders. That script validates the fields it consumes; this module validates
the one thing it cannot, because the claim points outside the README: boards
an author says they tested on must actually be targets the app builds for.

Vocabularies are duplicated here and in the renderer on purpose. The renderer
fails a docs build; these tests fail a source checkout, which is where a new
example is added.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"

REQUIRED_FIELDS = ("title", "tier", "capabilities", "summary", "status")
VALID_TIERS = {"basics", "capabilities", "integrations"}
VALID_STATUS = {"tested", "builds", "experimental"}


def example_names() -> list[str]:
    return sorted(p.parent.name for p in EXAMPLES_DIR.glob("*/nsx.yml"))


def read_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    data = yaml.safe_load(text[4:end]) or {}
    return data if isinstance(data, dict) else {}


def supported_boards(nsx_cfg: dict) -> list[str]:
    """Return every board the app declares a target for."""

    targets = nsx_cfg.get("targets")
    if isinstance(targets, dict):
        supported = targets.get("supported", [])
        if isinstance(supported, dict):
            return list(supported)
        if isinstance(supported, list):
            return [b for b in supported if isinstance(b, str)]
        return []
    # Legacy single-target form.
    target = nsx_cfg.get("target")
    board = target.get("board") if isinstance(target, dict) else None
    return [board] if isinstance(board, str) and board else []


@pytest.fixture(params=example_names())
def example(request: pytest.FixtureRequest) -> str:
    return request.param


def test_there_are_examples_to_check() -> None:
    assert example_names(), "no examples/<name>/nsx.yml found"


def test_readme_declares_every_required_field(example: str) -> None:
    fm = read_front_matter(EXAMPLES_DIR / example / "README.md")
    missing = [key for key in REQUIRED_FIELDS if not fm.get(key)]
    assert not missing, f"examples/{example}/README.md front matter is missing {missing}"


def test_tier_and_status_use_the_known_vocabulary(example: str) -> None:
    fm = read_front_matter(EXAMPLES_DIR / example / "README.md")
    assert fm.get("tier") in VALID_TIERS, (
        f"examples/{example}/README.md tier={fm.get('tier')!r}; expected one of {sorted(VALID_TIERS)}"
    )
    assert fm.get("status") in VALID_STATUS, (
        f"examples/{example}/README.md status={fm.get('status')!r}; "
        f"expected one of {sorted(VALID_STATUS)}"
    )


def test_tested_boards_are_targets_the_app_builds_for(example: str) -> None:
    fm = read_front_matter(EXAMPLES_DIR / example / "README.md")
    tested = fm.get("boards_tested") or []
    assert isinstance(tested, list), f"examples/{example}/README.md boards_tested must be a list"
    nsx_cfg = yaml.safe_load((EXAMPLES_DIR / example / "nsx.yml").read_text(encoding="utf-8")) or {}
    boards = supported_boards(nsx_cfg)
    stray = [b for b in tested if b not in boards]
    assert not stray, (
        f"examples/{example}/README.md boards_tested {stray} are not in "
        f"examples/{example}/nsx.yml targets.supported {boards}"
    )
