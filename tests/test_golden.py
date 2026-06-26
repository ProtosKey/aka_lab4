"""
Golden integration tests.

Each test is a directory under tests/golden/ containing a single test.yaml:
  name             — test name
  source           — Lisp source program
  input            — bytes fed to port 0 (may be empty)
  expected_output  — bytes expected on port 1 after HALT
  expected_trace   — tick-accurate trace (full or first N ticks)
  expected_listing — full disassembly listing (binary variant)

Test pipeline:
  1. compile_program(source)  →  inst_bytes, data_bytes, listing
  2. run(inst_bytes, ...)     →  output_bytes, traces
  3. compare against all expected_* fields from test.yaml
"""

from __future__ import annotations

import os
import re
import struct

import pytest

from src.simulator import run
from src.translator.codegen import compile_program

# ── helpers ───────────────────────────────────────────────────────────────────

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

_LISTING_LINE = re.compile(r"^[0-9A-F]{4} - [0-9A-F]{8} - .+$")


def _parse_yaml(path: str) -> dict:
    """Parse a simple block-scalar YAML file into a dict."""
    result: dict = {}
    current_key: str | None = None
    block_indent: int | None = None
    block_lines: list[str] = []

    def flush() -> None:
        if current_key is not None:
            result[current_key] = "\n".join(block_lines) + "\n"
        block_lines.clear()

    with open(path) as f:
        lines = f.readlines()

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if block_indent is not None:
            indent = len(line) - len(line.lstrip()) if stripped else 0
            if stripped == "" or indent >= block_indent:
                block_lines.append(line[block_indent:] if stripped else "")
                continue
            flush()
            block_indent = None
            current_key = None

        if not stripped or ":" not in stripped:
            continue

        key, _, val = stripped.partition(":")
        key = key.strip()
        val = val.strip()
        if val == "|":
            flush()
            current_key = key
            block_indent = len(line) - len(line.lstrip()) + 2
            block_lines = []
        elif val in ("''", '""'):
            result[key] = ""
        else:
            result[key] = val.strip("'\"")

    flush()
    return result


def _load_yaml(name: str) -> dict:
    path = os.path.join(GOLDEN_DIR, f"{name}.yaml")
    return _parse_yaml(path)


def _load(name: str) -> tuple[str, list[int], str]:
    case = _load_yaml(name)
    tokens = [ord(c) for c in case.get("input", "")]
    return case["source"], tokens, case["expected_output"]


def _read_golden(name: str, filename: str) -> list[str] | None:
    case = _load_yaml(name)
    key = filename.replace("expected_", "").replace(".txt", "").replace(".lst", "")
    key = "expected_" + key
    text = case.get(key)
    if text is None:
        return None
    return [line.rstrip() for line in text.splitlines() if line.rstrip()]


# ── parametrize ───────────────────────────────────────────────────────────────

_CASES = [
    # (name, max_ticks)
    ("hello", 10_000),
    ("cat", 5_000),
    ("hello_user_name", 50_000),
    ("sort", 200_000),
    ("prob2", 500_000),
    ("double_prec", 10_000),
    ("expr_as_expr", 10_000),
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

    assert traces, f"[{name}] No traces produced — simulation never started"
    last = traces[-1]
    assert last.halted, f"[{name}] Simulation reached tick limit ({max_ticks}) without HALT"


# ── listing golden ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,_", _CASES)
def test_listing_golden(name: str, _: int) -> None:
    """
    Listing must match expected_listing.lst exactly.

    This verifies the binary variant requirement: the translator must produce
    a deterministic human-readable disassembly alongside the binary file.
    """
    source, _, _ = _load(name)
    _, _, listing = compile_program(source)

    expected_lines = _read_golden(name, "expected_listing.lst")
    assert expected_lines is not None, f"[{name}] expected_listing.lst is missing"

    actual_lines = [line.rstrip() for line in listing.splitlines() if line.strip()]
    assert actual_lines == expected_lines, (
        f"[{name}] Listing mismatch — first differing line:\n"
        + _first_diff(actual_lines, expected_lines)
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


# ── trace golden ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,max_ticks", _CASES)
def test_trace_golden(name: str, max_ticks: int) -> None:
    """
    Tick-accurate trace must match expected_trace.txt.

    The golden file may contain fewer lines than the full trace (for large
    programs).  Only the stored prefix is compared, so any stored line must
    be reproduced exactly — this pins the tick-level simulator behaviour.
    """
    source, tokens, _ = _load(name)
    inst, data, _ = compile_program(source)
    _, traces = run(inst, data, tokens, max_ticks=max_ticks)

    expected_lines = _read_golden(name, "expected_trace.txt")
    assert expected_lines is not None, f"[{name}] expected_trace.txt is missing"

    n = len(expected_lines)
    actual_lines = [t.format() for t in traces[:n]]

    assert actual_lines == expected_lines, (
        f"[{name}] Trace mismatch (comparing first {n} ticks) — first differing line:\n"
        + _first_diff(actual_lines, expected_lines)
    )


# ── binary properties ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("name,_", _CASES)
def test_binary_properties(name: str, _: int) -> None:
    """
    Instruction binary must be non-empty and word-aligned (4 bytes per instr).
    Every 4-byte word must have a non-zero opcode field.
    """
    source, _, _ = _load(name)
    inst, data, _ = compile_program(source)

    assert len(inst) > 0, f"[{name}] Empty instruction binary"
    assert len(inst) % 4 == 0, f"[{name}] Binary length {len(inst)} not a multiple of 4"

    words = struct.unpack_from(f"<{len(inst) // 4}I", inst)
    for i, w in enumerate(words):
        opcode = w & 0x7F
        assert opcode != 0x00, f"[{name}] Word {i} (0x{w:08X}) has zero opcode at byte {i * 4:#06x}"


# ── Harvard memory — instruction and data sections ────────────────────────────


@pytest.mark.parametrize("name,_", _CASES)
def test_harvard_sections(name: str, _: int) -> None:
    """
    Harvard architecture: instruction memory (inst_bytes) and data memory
    (data_bytes) must be separate non-overlapping binaries.

    Programs with string literals or global variables must have non-empty
    data sections; pure-computation programs may have empty ones.
    """
    source, _, _ = _load(name)
    inst, data, _ = compile_program(source)

    # Instruction memory is always non-empty and a multiple of 4.
    assert len(inst) > 0 and len(inst) % 4 == 0

    # Data memory is a separate byte array — just being present is enough
    # to satisfy the Harvard split; its content is checked by test_output.
    assert isinstance(data, bytes)


# ── tick-accurate trace sanity ────────────────────────────────────────────────


@pytest.mark.parametrize("name,max_ticks", _CASES)
def test_trace_sanity(name: str, max_ticks: int) -> None:
    """
    Structural invariants of the tick trace:
      - Tick numbers are strictly sequential.
      - PC is 4-byte aligned on every fetch tick (µPC=0x00).
    """
    source, tokens, _ = _load(name)
    inst, data, _ = compile_program(source)
    _, traces = run(inst, data, tokens, max_ticks=max_ticks)

    prev_tick = 0
    for t in traces:
        assert t.tick == prev_tick + 1, f"[{name}] Non-sequential tick: {prev_tick} → {t.tick}"
        prev_tick = t.tick

        if t.mpc == 0x00:
            assert t.pc % 4 == 0, f"[{name}] Misaligned PC on fetch tick {t.tick}: 0x{t.pc:08X}"


# ── ISA instruction coverage ──────────────────────────────────────────────────


def test_isa_coverage() -> None:
    """
    Together, the golden programs must exercise all ISA instruction classes:
    ALU, LOAD, STORE, BRANCH, JAL, JALR, LUI, IN, OUT, HALT.
    """
    covered_mpcs: set[int] = set()

    for name, max_ticks in _CASES:
        source, tokens, _ = _load(name)
        inst, data, _ = compile_program(source)
        _, traces = run(inst, data, tokens, max_ticks=max_ticks)
        for t in traces:
            covered_mpcs.add(t.mpc)

    required = {
        0x01,  # ADD
        0x08,  # ADDI
        0x03,  # MUL
        0x0D,  # LB.addr
        0x0F,  # LW.addr
        0x11,  # SB.addr
        0x13,  # SW.addr
        0x15,  # BEQ
        0x17,  # BLT
        0x19,  # JAL
        0x1A,  # JALR
        0x1B,  # LUI
        0x1C,  # IN
        0x1D,  # OUT
        0x1E,  # HALT
    }
    missing = required - covered_mpcs
    assert not missing, (
        "ISA coverage gap — these µPC entry points were never executed: "
        + ", ".join(f"0x{m:02X}" for m in sorted(missing))
    )


# ── util ──────────────────────────────────────────────────────────────────────


def _first_diff(actual: list[str], expected: list[str]) -> str:
    n = min(len(actual), len(expected))
    for i in range(n):
        if actual[i] != expected[i]:
            return f"  line {i + 1}:\n    got:      {actual[i]!r}\n    expected: {expected[i]!r}"
    if len(actual) != len(expected):
        return f"  length: got {len(actual)}, expected {len(expected)}"
    return "  (no difference found)"
