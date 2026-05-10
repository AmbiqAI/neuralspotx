#!/usr/bin/env python3
"""Verify that every example's vendored ``cmake/nsx/`` matches the canonical copy.

REVIEW2 item F4: each example carries its own ``cmake/nsx/`` tree (vendored
on purpose so users can build any example without first installing nsx).
This script byte-compares every file under ``src/neuralspotx/cmake/`` to
its counterpart in each ``examples/*/cmake/nsx/`` and exits non-zero on
the first mismatch.

The per-app ``modules.cmake`` file is **expected** to differ (each
example declares its own module set), so it is excluded from the diff.

Run locally:

    python scripts/check_vendored_cmake.py

CI invokes this from the ``cmake-vendor-diff`` job in
``.github/workflows/ci.yml``.
"""

from __future__ import annotations

import filecmp
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CANONICAL = REPO_ROOT / "src" / "neuralspotx" / "cmake"
EXAMPLES = REPO_ROOT / "examples"

# Files under examples/<app>/cmake/nsx that are intentionally per-app and
# must NOT be compared against the canonical tree.
PER_APP_FILES = frozenset({"modules.cmake"})


def _canonical_files() -> list[Path]:
    return sorted(p for p in CANONICAL.rglob("*") if p.is_file())


def _check_example(example_dir: Path, canonical_files: list[Path]) -> list[str]:
    vendor_root = example_dir / "cmake" / "nsx"
    if not vendor_root.is_dir():
        return [f"{example_dir.name}: missing cmake/nsx/ vendor tree"]

    errors: list[str] = []
    for canonical in canonical_files:
        rel = canonical.relative_to(CANONICAL)
        vendored = vendor_root / rel
        if not vendored.exists():
            errors.append(f"{example_dir.name}: missing vendored file {rel}")
            continue
        if not filecmp.cmp(canonical, vendored, shallow=False):
            errors.append(
                f"{example_dir.name}: drift in {rel} (differs from src/neuralspotx/cmake/{rel})"
            )

    # Also flag any extra files in the vendor tree that aren't either
    # canonical or in the per-app allowlist — that would indicate the
    # canonical tree shrank and one example never followed.
    canonical_rels = {p.relative_to(CANONICAL) for p in canonical_files}
    for vendored in vendor_root.rglob("*"):
        if not vendored.is_file():
            continue
        rel = vendored.relative_to(vendor_root)
        if rel in canonical_rels:
            continue
        if rel.name in PER_APP_FILES and len(rel.parts) == 1:
            continue
        errors.append(
            f"{example_dir.name}: orphan vendored file {rel} "
            f"(not in canonical src/neuralspotx/cmake/ and not in PER_APP_FILES)"
        )
    return errors


def main() -> int:
    if not CANONICAL.is_dir():
        print(f"error: canonical cmake tree missing: {CANONICAL}", file=sys.stderr)
        return 2

    canonical_files = _canonical_files()
    if not canonical_files:
        print(f"error: canonical cmake tree is empty: {CANONICAL}", file=sys.stderr)
        return 2

    examples = sorted(p for p in EXAMPLES.iterdir() if p.is_dir())
    if not examples:
        print(f"error: no examples under {EXAMPLES}", file=sys.stderr)
        return 2

    all_errors: list[str] = []
    for example in examples:
        if not (example / "cmake" / "nsx").is_dir():
            # Not every example dir necessarily vendors cmake/nsx (e.g.
            # tooling-only directories). Skip silently.
            continue
        all_errors.extend(_check_example(example, canonical_files))

    if all_errors:
        print("Vendored cmake/nsx/ trees have drifted from src/neuralspotx/cmake/:")
        for err in all_errors:
            print(f"  - {err}")
        print()
        print(
            "Refresh the affected example(s) by re-running the configure step "
            "or by copying src/neuralspotx/cmake/* into the example's cmake/nsx/."
        )
        return 1

    print(
        f"OK: {len(examples)} example(s) match canonical "
        f"src/neuralspotx/cmake/ ({len(canonical_files)} file(s))."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
