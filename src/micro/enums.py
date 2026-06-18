"""Control signal enumerations matching microcode.md §1."""

from enum import IntEnum


class AluOp(IntEnum):
    """3-bit binary ALU operation code (microcode.md §1.1)."""
    NOP = 0b000
    ADD = 0b001
    SUB = 0b010
    MUL = 0b011
    SLL = 0b100
    SRL = 0b101
    AND = 0b110
    OR  = 0b111


class MemOp(IntEnum):
    """3-bit binary data-memory operation code (microcode.md §1.2)."""
    NONE  = 0b000
    RD_B  = 0b001
    RD_W  = 0b010
    WR_B  = 0b011
    WR_W  = 0b100


class IoOp(IntEnum):
    """2-bit I/O port operation code (microcode.md §1)."""
    NONE = 0b00
    IN   = 0b01
    OUT  = 0b10


class WbSel(IntEnum):
    """3-bit write-back mux selector (microcode.md §1.3)."""
    NONE   = 0b000
    ALU    = 0b001
    MEM    = 0b010
    PC4    = 0b011
    IMM_HI = 0b100
    IO_IN  = 0b101


class PcSrc(IntEnum):
    """3-bit PC mux selector including branch conditions (microcode.md §1.4)."""
    PC4    = 0b000
    PC_IMM = 0b001
    ALU    = 0b010
    BR_EQ  = 0b011
    BR_NE  = 0b100
    BR_LT  = 0b101
    BR_GE  = 0b110


class Seq(IntEnum):
    """2-bit µPC sequencer mode (microcode.md §1.5)."""
    NEXT   = 0b00
    FETCH  = 0b01
    DECODE = 0b10
    HALT   = 0b11
