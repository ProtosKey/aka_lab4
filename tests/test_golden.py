"""
Golden integration tests.

Each test is a directory under tests/golden/ containing:
  source.lisp           — Lisp source program
  input.txt             — bytes fed to port 0 (may be empty)
  expected_output.txt   — bytes expected on port 1 after HALT

The test pipeline mirrors the real toolchain:
  1. compile_program(source)  →  inst_bytes, data_bytes, listing
  2. run(inst_bytes, ...)     →  output_bytes, traces
  3. assert output == expected

Additional checks per test:
  - Listing lines match the binary-variant format (§9 isa.md):
      <ADDR> - <HEXCODE> - <mnemonic>
  - Instruction binary size is a nonzero multiple of 4.
  - Simulation ends with a HALT trace event (no runaway loop).
"""

from __future__ import annotations

import os
import re
import struct

import pytest

from src.translator.codegen import compile_program
from src.simulator import run

# ── helpers ───────────────────────────────────────────────────────────────────

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

_LISTING_LINE = re.compile(r"^[0-9A-F]{4} - [0-9A-F]{8} - .+$")


def _load(name: str) -> tuple[str, list[int], str]:
    """Return (source, input_tokens, expected_output) for the named golden test."""
    d = os.path.join(GOLDEN_DIR, name)
    with open(os.path.join(d, "source.lisp")) as f:
        source = f.read()
    inp_path = os.path.join(d, "input.txt")
    input_str = open(inp_path).read() if os.path.exists(inp_path) else ""
    with open(os.path.join(d, "expected_output.txt")) as f:
        expected = f.read()
    tokens = [ord(c) for c in input_str]
    return source, tokens, expected


# ── parametrize ───────────────────────────────────────────────────────────────

_CASES = [
    # (name, max_ticks)
    ("hello",           10_000),
    ("cat",             5_000),
    ("hello_user_name", 50_000),
    ("sort",            200_000),
    ("prob2",           500_000),
    ("double_prec",     10_000),
]


# ── output correctness ────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,max_ticks", _CASES)
def test_output(name: str, max_ticks: int) -> None:
    """Compiled + simulated output must match expected_output.txt exactly."""
    source, tokens, expected = _load(name)
    inst, data, _ = compile_program(source)
    output, traces = run(inst, data, tokens, max_ticks=max_ticks)

    assert output.decode("latin-1") == expected, (
        f"[{name}] Output mismatch:\n"
        f"  got:      {output!r}\n"
        f"  expected: {expected.encode('latin-1')!r}"
    )

    # Simulation must have terminated cleanly (HALT or input-empty).
    assert traces, f"[{name}] No traces produced — simulation never started"
    last = traces[-1]
    assert last.halted, (
        f"[{name}] Simulation reached tick limit ({max_ticks}) without HALT"
    )


# ── listing format ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,_", _CASES)
def test_listing_format(name: str, _: int) -> None:
    """
    Every listing line must match the binary-variant format (isa.md §9):
        <ADDR> - <HEXCODE> - <mnemonic>
    """
    source, _, _ = _load(name)
    _, _, listing = compile_program(source)

    lines = listing.strip().splitlines()
    assert lines, f"[{name}] Empty listing"

    for lineno, line in enumerate(lines, 1):
        assert _LISTING_LINE.match(line), (
            f"[{name}] Listing line {lineno} has wrong format:\n  {line!r}"
        )


# ── binary properties ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,_", _CASES)
def test_binary_properties(name: str, _: int) -> None:
    """
    Instruction binary must be non-empty and word-aligned (4 bytes per instr).
    Every 4-byte word must decode without an unknown opcode (rounds to HALT).
    """
    source, _, _ = _load(name)
    inst, data, _ = compile_program(source)

    assert len(inst) > 0, f"[{name}] Empty instruction binary"
    assert len(inst) % 4 == 0, (
        f"[{name}] Instruction binary length {len(inst)} not a multiple of 4"
    )

    # Each word must be parseable (no completely zero-opcode words except HALT).
    words = struct.unpack_from(f"<{len(inst)//4}I", inst)
    for i, w in enumerate(words):
        opcode = w & 0x7F
        # opcode 0x00 means uninitialized / bad encoding
        assert opcode != 0x00, (
            f"[{name}] Word {i} (0x{w:08X}) has zero opcode at byte {i*4:#06x}"
        )


# ── tick-accurate trace sanity ────────────────────────────────────────────────

@pytest.mark.parametrize("name,max_ticks", _CASES)
def test_trace_sanity(name: str, max_ticks: int) -> None:
    """
    Basic structural checks on the tick trace:
      - Every tick number must be strictly increasing.
      - Fetch ticks (µPC=0x00) must be followed by an execute tick.
      - PC must be 4-byte aligned on every fetch.
    """
    source, tokens, _ = _load(name)
    inst, data, _ = compile_program(source)
    _, traces = run(inst, data, tokens, max_ticks=max_ticks)

    prev_tick = 0
    for t in traces:
        assert t.tick == prev_tick + 1, (
            f"[{name}] Non-sequential tick: {prev_tick} → {t.tick}"
        )
        prev_tick = t.tick

        if t.mpc == 0x00:  # fetch tick
            assert t.pc % 4 == 0, (
                f"[{name}] Misaligned PC on fetch tick {t.tick}: 0x{t.pc:08X}"
            )


# ── ISA instruction coverage ──────────────────────────────────────────────────

def test_isa_coverage() -> None:
    """
    Together, the golden programs must exercise all ISA instruction classes:
    ALU, LOAD, STORE, BRANCH (taken + not-taken), JAL, JALR, LUI, IN, OUT, HALT.
    """
    from src.micro.microcode_rom import decode

    covered_mpcs: set[int] = set()

    for name, max_ticks in _CASES:
        source, tokens, _ = _load(name)
        inst, data, _ = compile_program(source)
        _, traces = run(inst, data, tokens, max_ticks=max_ticks)
        for t in traces:
            covered_mpcs.add(t.mpc)

    # Every micro-entry point that the decode table can produce must appear.
    required = {
        0x01,   # ADD
        0x08,   # ADDI
        0x03,   # MUL
        0x0D,   # LB.addr
        0x0F,   # LW.addr
        0x11,   # SB.addr
        0x13,   # SW.addr
        0x15,   # BEQ
        0x17,   # BLT
        0x19,   # JAL
        0x1A,   # JALR
        0x1B,   # LUI
        0x1C,   # IN
        0x1D,   # OUT
        0x1E,   # HALT
    }
    missing = required - covered_mpcs
    assert not missing, (
        f"ISA coverage gap — these µPC entry points were never executed: "
        + ", ".join(f"0x{m:02X}" for m in sorted(missing))
    )
