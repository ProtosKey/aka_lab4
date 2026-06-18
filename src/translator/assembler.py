from __future__ import annotations

import struct
from dataclasses import dataclass

X0 = 0
RA = 1
SP = 2
GP = 3
FP = 8
T0 = 5
T1 = 6
A0 = 10
A1 = 11
A2 = 12
A3 = 13
A4 = 14
A5 = 15
A6 = 16
A7 = 17

ARG_REGS = [A0, A1, A2, A3, A4, A5, A6, A7]
REG_NAMES = {
    0: "x0",
    1: "ra",
    2: "sp",
    3: "gp",
    4: "tp",
    5: "t0",
    6: "t1",
    7: "t2",
    8: "fp",
    9: "s1",
    10: "a0",
    11: "a1",
    12: "a2",
    13: "a3",
    14: "a4",
    15: "a5",
    16: "a6",
    17: "a7",
    18: "s2",
    19: "s3",
    20: "s4",
    21: "s5",
    22: "s6",
    23: "s7",
    24: "s8",
    25: "s9",
    26: "s10",
    27: "s11",
    28: "t3",
    29: "t4",
    30: "t5",
    31: "t6",
}


def _rn(r: int) -> str:
    return REG_NAMES.get(r, f"x{r}")


_OP = 0b0110011
_OP_IMM = 0b0010011
_LOAD = 0b0000011
_STORE = 0b0100011
_BRANCH = 0b1100011
_JAL_OP = 0b1101111
_JALR_OP = 0b1100111
_LUI_OP = 0b0110111
_IO_IN = 0b0001011
_IO_OUT = 0b0101011
_SYSTEM = 0b1110011


def _pack_i(opcode: int, rd: int, f3: int, rs1: int, imm: int) -> int:
    return (
        (opcode & 0x7F)
        | ((rd & 0x1F) << 7)
        | ((f3 & 0x7) << 12)
        | ((rs1 & 0x1F) << 15)
        | ((imm & 0xFFF) << 20)
    )


def _pack_r(opcode: int, rd: int, f3: int, rs1: int, rs2: int, f7: int) -> int:
    return (
        (opcode & 0x7F)
        | ((rd & 0x1F) << 7)
        | ((f3 & 0x7) << 12)
        | ((rs1 & 0x1F) << 15)
        | ((rs2 & 0x1F) << 20)
        | ((f7 & 0x7F) << 25)
    )


def _pack_s(opcode: int, f3: int, rs1: int, rs2: int, imm: int) -> int:
    return (
        (opcode & 0x7F)
        | ((imm & 0x1F) << 7)
        | ((f3 & 0x7) << 12)
        | ((rs1 & 0x1F) << 15)
        | ((rs2 & 0x1F) << 20)
        | (((imm >> 5) & 0x7F) << 25)
    )


def _pack_b(opcode: int, f3: int, rs1: int, rs2: int, imm: int) -> int:
    b = imm
    return (
        (opcode & 0x7F)
        | (((b >> 11) & 0x1) << 7)
        | (((b >> 1) & 0xF) << 8)
        | ((f3 & 0x7) << 12)
        | ((rs1 & 0x1F) << 15)
        | ((rs2 & 0x1F) << 20)
        | (((b >> 5) & 0x3F) << 25)
        | (((b >> 12) & 0x1) << 31)
    )


def _pack_u(opcode: int, rd: int, imm20: int) -> int:
    return (opcode & 0x7F) | ((rd & 0x1F) << 7) | ((imm20 & 0xFFFFF) << 12)


def _pack_j(opcode: int, rd: int, imm: int) -> int:
    b = imm
    return (
        (opcode & 0x7F)
        | ((rd & 0x1F) << 7)
        | (((b >> 12) & 0xFF) << 12)
        | (((b >> 11) & 0x1) << 20)
        | (((b >> 1) & 0x3FF) << 21)
        | (((b >> 20) & 0x1) << 31)
    )


def _b_imm_bits(imm: int) -> int:
    """Encode B-format immediate into the correct bit positions (no opcode)."""
    b = imm & 0x1FFE  # keep bits [12:1]
    return (
        (((b >> 11) & 0x1) << 7)
        | (((b >> 1) & 0xF) << 8)
        | (((b >> 5) & 0x3F) << 25)
        | (((b >> 12) & 0x1) << 31)
    )


def _j_imm_bits(imm: int) -> int:
    """Encode J-format immediate into the correct bit positions (no opcode/rd)."""
    b = imm & 0x1FFFFE
    return (
        (((b >> 12) & 0xFF) << 12)
        | (((b >> 11) & 0x1) << 20)
        | (((b >> 1) & 0x3FF) << 21)
        | (((b >> 20) & 0x1) << 31)
    )


def _hi_lo(value: int) -> tuple[int, int]:
    """Split a 32-bit constant into (hi20, lo12_signed) for LUI+ADDI."""
    v = value & 0xFFFFFFFF
    hi = ((v + 0x800) >> 12) & 0xFFFFF
    lo = v - (hi << 12)  # signed, fits in [-2048, 2047]
    return hi, lo


@dataclass
class ListingEntry:
    addr: int
    word: int
    mnem: str


@dataclass
class _Fixup:
    idx: int  # word index in _words
    instr_pc: int  # byte address of this instruction
    label: str
    typ: str  # 'B' or 'J'
    base: int  # instruction word with imm bits = 0


class Assembler:
    """
    Accumulates instruction words, tracks labels, resolves fixups.
    Also maintains a human-readable listing.
    """

    def __init__(self) -> None:
        self._words: list[int] = []
        self._mnems: list[str] = []
        self._labels: dict[str, int] = {}
        self._fixups: list[_Fixup] = []
        self._cnt: int = 0  # label counter

    def pc(self) -> int:
        return len(self._words) * 4

    def new_label(self, prefix: str = "L") -> str:
        self._cnt += 1
        return f".{prefix}{self._cnt}"

    def place_label(self, name: str) -> None:
        self._labels[name] = self.pc()

    def _raw(self, word: int, mnem: str) -> None:
        self._words.append(word & 0xFFFFFFFF)
        self._mnems.append(mnem)

    def _fixup_raw(self, base: int, label: str, mnem: str, typ: str) -> None:
        f = _Fixup(len(self._words), self.pc(), label, typ, base)
        self._fixups.append(f)
        self._raw(0, mnem)

    def addi(self, rd: int, rs1: int, imm: int) -> None:
        self._raw(_pack_i(_OP_IMM, rd, 0, rs1, imm), f"addi {_rn(rd)}, {_rn(rs1)}, {imm}")

    def add(self, rd: int, rs1: int, rs2: int) -> None:
        self._raw(
            _pack_r(_OP, rd, 0b000, rs1, rs2, 0b0000000), f"add {_rn(rd)}, {_rn(rs1)}, {_rn(rs2)}"
        )

    def sub(self, rd: int, rs1: int, rs2: int) -> None:
        self._raw(
            _pack_r(_OP, rd, 0b000, rs1, rs2, 0b0100000), f"sub {_rn(rd)}, {_rn(rs1)}, {_rn(rs2)}"
        )

    def mul(self, rd: int, rs1: int, rs2: int) -> None:
        self._raw(
            _pack_r(_OP, rd, 0b000, rs1, rs2, 0b0000001), f"mul {_rn(rd)}, {_rn(rs1)}, {_rn(rs2)}"
        )

    def lui(self, rd: int, imm20: int) -> None:
        self._raw(_pack_u(_LUI_OP, rd, imm20), f"lui {_rn(rd)}, 0x{imm20:05X}")

    def lw(self, rd: int, rs1: int, imm: int) -> None:
        self._raw(_pack_i(_LOAD, rd, 0b010, rs1, imm), f"lw {_rn(rd)}, {imm}({_rn(rs1)})")

    def lb(self, rd: int, rs1: int, imm: int) -> None:
        self._raw(_pack_i(_LOAD, rd, 0b000, rs1, imm), f"lb {_rn(rd)}, {imm}({_rn(rs1)})")

    def sw(self, rs1: int, rs2: int, imm: int) -> None:
        self._raw(_pack_s(_STORE, 0b010, rs1, rs2, imm), f"sw {_rn(rs2)}, {imm}({_rn(rs1)})")

    def sb(self, rs1: int, rs2: int, imm: int) -> None:
        self._raw(_pack_s(_STORE, 0b000, rs1, rs2, imm), f"sb {_rn(rs2)}, {imm}({_rn(rs1)})")

    def beq(self, rs1: int, rs2: int, label: str) -> None:
        base = _pack_b(_BRANCH, 0b000, rs1, rs2, 0)
        self._fixup_raw(base, label, f"beq {_rn(rs1)}, {_rn(rs2)}, {label}", "B")

    def bne(self, rs1: int, rs2: int, label: str) -> None:
        base = _pack_b(_BRANCH, 0b001, rs1, rs2, 0)
        self._fixup_raw(base, label, f"bne {_rn(rs1)}, {_rn(rs2)}, {label}", "B")

    def blt(self, rs1: int, rs2: int, label: str) -> None:
        base = _pack_b(_BRANCH, 0b100, rs1, rs2, 0)
        self._fixup_raw(base, label, f"blt {_rn(rs1)}, {_rn(rs2)}, {label}", "B")

    def bge(self, rs1: int, rs2: int, label: str) -> None:
        base = _pack_b(_BRANCH, 0b101, rs1, rs2, 0)
        self._fixup_raw(base, label, f"bge {_rn(rs1)}, {_rn(rs2)}, {label}", "B")

    def jal(self, rd: int, label: str) -> None:
        base = _pack_j(_JAL_OP, rd, 0)
        self._fixup_raw(base, label, f"jal {_rn(rd)}, {label}", "J")

    def jalr(self, rd: int, rs1: int, imm: int = 0) -> None:
        self._raw(_pack_i(_JALR_OP, rd, 0, rs1, imm), f"jalr {_rn(rd)}, {_rn(rs1)}, {imm}")

    def in_port(self, rd: int, port: int) -> None:
        self._raw(_pack_i(_IO_IN, rd, 0, X0, port), f"in {_rn(rd)}, {port}")

    def out_port(self, rs1: int, port: int) -> None:
        self._raw(_pack_s(_IO_OUT, 0, rs1, X0, port), f"out {_rn(rs1)}, {port}")

    def halt(self) -> None:
        self._raw(_pack_i(_SYSTEM, X0, 0, X0, 0), "halt")

    def load_const(self, rd: int, value: int) -> None:
        """Load an arbitrary 32-bit constant into rd."""
        v = value & 0xFFFFFFFF
        if v >= 0x80000000:
            sv = v - 0x100000000
        else:
            sv = v
        if -2048 <= sv < 2048:
            self.addi(rd, X0, sv)
        else:
            hi, lo = _hi_lo(v)
            self.lui(rd, hi)
            if lo != 0:
                self.addi(rd, rd, lo & 0xFFF)

    def resolve(self) -> list[int]:
        words = list(self._words)
        for f in self._fixups:
            if f.label not in self._labels:
                raise RuntimeError(f"Undefined label: {f.label!r}")
            target = self._labels[f.label]
            offset = target - f.instr_pc
            if f.typ == "B":
                imm_bits = _b_imm_bits(offset)
            else:
                imm_bits = _j_imm_bits(offset)
            words[f.idx] = (f.base | imm_bits) & 0xFFFFFFFF
        return words

    def to_bytes(self) -> bytes:
        words = self.resolve()
        return struct.pack(f"<{len(words)}I", *words)

    def listing(self) -> list[ListingEntry]:
        words = self.resolve()
        return [ListingEntry(i * 4, words[i], self._mnems[i]) for i in range(len(words))]

    def listing_text(self) -> str:
        lines = []
        for e in self.listing():
            lines.append(f"{e.addr:04X} - {e.word:08X} - {e.mnem}")
        return "\n".join(lines)
