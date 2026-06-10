#!/usr/bin/env python3
"""Generate resnet_sample_data.h from the Ambiq model-zoo golden.npz fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


LABELS = [
    "airplane",
    "automobile",
    "bird",
    "cat",
    "deer",
    "dog",
    "frog",
    "horse",
    "ship",
    "truck",
]


def _format_int8_array(name: str, values: np.ndarray) -> str:
    flattened = values.astype(np.int8).reshape(-1)
    lines = []
    for start in range(0, len(flattened), 16):
        chunk = flattened[start : start + 16]
        joined = ", ".join(str(int(v)) for v in chunk)
        suffix = "," if start + 16 < len(flattened) else ""
        lines.append(f"    {joined}{suffix}")
    body = "\n".join(lines)
    return f"static const int8_t {name}[{len(flattened)}] = {{\n{body}\n}};\n"


def generate_header(golden_path: Path, output_path: Path) -> None:
    data = np.load(golden_path)
    if "x" not in data or "y" not in data:
        raise KeyError("golden.npz must contain 'x' and 'y' arrays")

    input_values = data["x"]
    output_values = data["y"]
    expected_index = int(np.argmax(output_values.reshape(-1)))

    label_lines = "\n".join(f'    "{label}",' for label in LABELS[:-1])
    label_lines += f'\n    "{LABELS[-1]}"'

    contents = f"""#pragma once

#include <stdint.h>

#define RESNET_GOLDEN_INPUT_SIZE {input_values.size}
#define RESNET_GOLDEN_OUTPUT_SIZE {output_values.size}
#define RESNET_GOLDEN_EXPECTED_INDEX {expected_index}

static const char *const kResnetLabels[RESNET_GOLDEN_OUTPUT_SIZE] = {{
{label_lines}
}};

{_format_int8_array("kResnetGoldenInput", input_values)}

{_format_int8_array("kResnetGoldenOutput", output_values)}
"""

    output_path.write_text(contents)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--golden", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    generate_header(args.golden, args.output)


if __name__ == "__main__":
    main()
