#!/usr/bin/env python3
"""Reject deferred-work markers that carry no tracking reference.

pre-commit passes the staged files as positional arguments. A line is flagged
when it contains one of the uppercase whole-word markers below and that marker
is not immediately followed by ``(#<issue-number>)`` or ``(verify)``.

A marker immediately followed by a quote character is treated as string data
rather than a marker, so tests and templates that assert on the literal word
are not flagged.

Exit code 0 when every file is clean, 1 when at least one line is flagged.
Files that cannot be decoded as UTF-8 are skipped.
"""

from __future__ import annotations

import re
import sys

_NAMES = ("TODO", "FIXME", "HACK")
_MARKER = re.compile(r"\b(?:" + "|".join(_NAMES) + r")\b")
_REFERENCED = re.compile(r"\((?:#\d+|verify)\)")
# Tuple, not a string: ``""[:1] in "..."`` is true for every string and would
# silently skip a marker at end of file.
_QUOTES = ('"', "'", "`")

_ADVICE = (
    "reference the tracking issue: TODO(#123) ..., "
    "or TODO(verify) for claims awaiting a source of record"
)


def _failures_in_line(path: str, number: int, line: str) -> list[str]:
    hits: list[str] = []
    for match in _MARKER.finditer(line):
        rest = line[match.end() :]
        if rest[:1] in _QUOTES:
            continue
        if _REFERENCED.match(rest):
            continue
        hits.append(f"{path}:{number}: bare {match.group()} - {_ADVICE}")
    return hits


def _check(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as handle:
            failures: list[str] = []
            for number, line in enumerate(handle, start=1):
                failures.extend(_failures_in_line(path, number, line))
    except (OSError, UnicodeDecodeError):
        return []
    return failures


def main(argv: list[str]) -> int:
    failures: list[str] = []
    for path in argv:
        failures.extend(_check(path))
    for failure in failures:
        print(failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
