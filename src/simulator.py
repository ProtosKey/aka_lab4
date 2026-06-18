"""
Processor simulator entry point.

Usage:
    python -m src.simulator <prog.bin> [data.bin] [input]

Arguments:
    prog.bin   — binary instruction file (4 bytes per instruction, little-endian)
    data.bin   — binary data file (optional, loaded at data memory offset 0)
    input      — input string or path to input file (optional)

Output:
    Tick-accurate trace on stdout.
    Final output port buffer printed after HALT.
"""

from __future__ import annotations

import sys
import os

from src.micro.data_path import DataPath
from src.micro.control_unit import ControlUnit, TickTrace

# Simulator limits
MAX_TICKS = 1_000_000
DATA_MEM_SIZE = 64 * 1024  # 64 KiB data memory


def load_input(raw: str) -> list[int]:
    """Convert input string to list of byte values (code points & 0xFF)."""
    return [ord(c) & 0xFF for c in raw]


def run(
    inst_bytes:   bytes,
    data_bytes:   bytes = b"",
    input_tokens: list[int] | None = None,
    *,
    trace: bool = True,
    max_ticks: int = MAX_TICKS,
) -> tuple[bytes, list[TickTrace]]:
    """
    Run the simulator.

    Returns (output_bytes, traces).
    """
    dp = DataPath(
        inst_bytes   = inst_bytes,
        data_size    = DATA_MEM_SIZE,
        data_bytes   = data_bytes,
        input_tokens = input_tokens or [],
    )
    cu = ControlUnit(dp)
    traces: list[TickTrace] = []

    for _ in range(max_ticks):
        try:
            t = cu.step()
        except RuntimeError as exc:
            print(f"SIMULATOR ERROR: {exc}", file=sys.stderr)
            break
        if t is None:
            break
        if trace:
            traces.append(t)
        if t.halted:
            break
    else:
        print("WARNING: max tick limit reached", file=sys.stderr)

    return dp.output_bytes, traces


def main(argv: list[str] | None = None) -> None:
    argv = argv or sys.argv[1:]
    if not argv:
        print(__doc__)
        sys.exit(1)

    prog_path = argv[0]
    data_path_arg = argv[1] if len(argv) > 1 else None
    input_arg  = argv[2] if len(argv) > 2 else ""

    with open(prog_path, "rb") as f:
        inst_bytes = f.read()

    data_bytes: bytes = b""
    if data_path_arg and os.path.exists(data_path_arg):
        with open(data_path_arg, "rb") as f:
            data_bytes = f.read()

    # Input: treat as a string if it doesn't look like a file path,
    # else load file contents.
    if input_arg and os.path.exists(input_arg):
        with open(input_arg) as f:
            input_str = f.read()
    else:
        input_str = input_arg

    input_tokens = load_input(input_str)

    output, traces = run(inst_bytes, data_bytes, input_tokens, trace=True)

    for t in traces:
        print(t.format())

    print()
    print(f"Output ({len(output)} bytes): {output.decode('latin-1', errors='replace')!r}")


if __name__ == "__main__":
    main()
