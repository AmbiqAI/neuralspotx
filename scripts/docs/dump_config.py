# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2026, Ambiq
"""Convert the configuration field manifest to JSON for the site build.

The manifest is YAML so it stays readable next to the validators it mirrors;
the renderer is Node and has no YAML reader, so the build converts it here.
The drift checks that make the manifest trustworthy live in
``tests/test_reference_generation.py``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

MANIFEST = Path(__file__).resolve().parent / "config_schema.yaml"

REQUIRED_SCHEMA_KEYS = {"id", "file", "title", "summary", "loader", "error", "fields", "example"}


def load(path: Path = MANIFEST) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schemas = data.get("schemas")
    if not isinstance(schemas, list) or not schemas:
        raise SystemExit(f"dump_config: {path} declares no schemas")
    for schema in schemas:
        missing = REQUIRED_SCHEMA_KEYS - set(schema)
        if missing:
            raise SystemExit(
                f"dump_config: schema {schema.get('id')!r} is missing {sorted(missing)}"
            )
        for field in schema["fields"]:
            if not field.get("path") or not field.get("description"):
                raise SystemExit(
                    f"dump_config: schema {schema['id']!r} has a field with no path or description"
                )
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, help="write the JSON here instead of stdout")
    args = parser.parse_args(argv)

    payload = json.dumps(load(), indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
