#!/usr/bin/env python3

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pte", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--outfile", default="model_pte.h")
    parser.add_argument("--section", default=".rodata.model_pte")
    args = parser.parse_args()

    data = args.pte.read_bytes()
    args.outdir.mkdir(parents=True, exist_ok=True)
    output = args.outdir / args.outfile

    with output.open("w", encoding="utf-8") as stream:
        stream.write(
            f"__attribute__((section(\"{args.section}\"), aligned(16))) "
            "const unsigned char model_pte[] = {"
        )
        for index, value in enumerate(data):
            if index % 32 == 0:
                stream.write("\n")
            stream.write(f"0x{value:02x}, ")
        stream.write("\n};\n")

    print(
        f"Input: {args.pte} with {len(data)} bytes. "
        f"Output: {output}. Section: {args.section}."
    )


if __name__ == "__main__":
    main()
