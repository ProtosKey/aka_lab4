"""
Lisp → RISC binary translator.

Usage:
    python -m src.translator <source.lisp> <output_stem>

Produces:
    <output_stem>.bin        — instruction memory binary
    <output_stem>.data.bin   — data memory initial image
    <output_stem>.lst        — disassembly listing

Example:
    python -m src.translator hello.lisp out/hello
"""

from __future__ import annotations

import os
import sys

from src.translator.codegen import compile_program


def main(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv[1:]
    if len(argv) < 2:
        print(__doc__)
        sys.exit(1)

    src_path, stem = argv[0], argv[1]
    with open(src_path) as f:
        src = f.read()

    inst_bytes, data_bytes, listing = compile_program(src)

    os.makedirs(os.path.dirname(stem) or ".", exist_ok=True)

    with open(stem + ".bin", "wb") as f:
        f.write(inst_bytes)
    with open(stem + ".data.bin", "wb") as f:
        f.write(data_bytes)
    with open(stem + ".lst", "w") as f:
        f.write(listing + "\n")

    print(f"inst:  {stem}.bin  ({len(inst_bytes)} bytes, {len(inst_bytes) // 4} instructions)")
    print(f"data:  {stem}.data.bin  ({len(data_bytes)} bytes)")
    print(f"list:  {stem}.lst")


if __name__ == "__main__":
    main()
