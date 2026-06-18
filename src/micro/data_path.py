"""DataPath — all processor state: registers, memories, I/O ports."""

from __future__ import annotations

from collections import deque

MASK32 = 0xFFFF_FFFF


def _sign32(v: int) -> int:
    """Unsigned 32-bit → signed Python int."""
    v &= MASK32
    return v if v < 0x8000_0000 else v - 0x1_0000_0000


def _u32(v: int) -> int:
    return v & MASK32


# Immediate decoders — one per instruction format (R has no immediate).


def _imm_i(instr: int) -> int:
    raw = (instr >> 20) & 0xFFF
    if raw & 0x800:
        raw |= ~0xFFF
    return _u32(raw)


def _imm_s(instr: int) -> int:
    lo = (instr >> 7) & 0x1F
    hi = (instr >> 25) & 0x7F
    raw = (hi << 5) | lo
    if raw & 0x800:
        raw |= ~0xFFF
    return _u32(raw)


def _imm_b(instr: int) -> int:
    b11 = (instr >> 7) & 0x1
    lo = (instr >> 8) & 0xF
    hi = (instr >> 25) & 0x3F
    b12 = (instr >> 31) & 0x1
    raw = (b12 << 12) | (b11 << 11) | (hi << 5) | (lo << 1)
    if b12:
        raw |= ~0x1FFF
    return _u32(raw)


def _imm_u(instr: int) -> int:
    return _u32((instr >> 12) << 12)


def _imm_j(instr: int) -> int:
    b20 = (instr >> 31) & 0x1
    lo10 = (instr >> 21) & 0x3FF
    b11 = (instr >> 20) & 0x1
    mid8 = (instr >> 12) & 0xFF
    raw = (b20 << 20) | (mid8 << 12) | (b11 << 11) | (lo10 << 1)
    if b20:
        raw |= ~0x1F_FFFF
    return _u32(raw)


_OP = 0b0110011
_OP_IMM = 0b0010011
_LOAD = 0b0000011
_STORE = 0b0100011
_BRANCH = 0b1100011
_JAL = 0b1101111
_JALR = 0b1100111
_LUI = 0b0110111
_IO_IN = 0b0001011
_IO_OUT = 0b0101011
_SYSTEM = 0b1110011

_S_FORMAT_OPCODES = {_STORE, _IO_OUT}
_B_FORMAT_OPCODES = {_BRANCH}
_J_FORMAT_OPCODES = {_JAL}
_U_FORMAT_OPCODES = {_LUI}


def decode_imm(instr: int) -> int:
    """Sign-extended immediate for the given instruction word."""
    op = instr & 0x7F
    if op in _S_FORMAT_OPCODES:
        return _imm_s(instr)
    if op in _B_FORMAT_OPCODES:
        return _imm_b(instr)
    if op in _J_FORMAT_OPCODES:
        return _imm_j(instr)
    if op in _U_FORMAT_OPCODES:
        return _imm_u(instr)
    return _imm_i(instr)


class DataPath:
    """All architectural state; CU calls methods here on each tick."""

    def __init__(
        self,
        inst_bytes: bytes | bytearray,
        data_size: int,
        data_bytes: bytes | bytearray = b"",
        input_tokens: list[int] | None = None,
    ) -> None:
        self.pc: int = 0
        self.ir: int = 0
        self.regs: list[int] = [0] * 32  # x0 hardwired to 0

        self._inst_mem: bytes | bytearray = inst_bytes

        self._data_mem: bytearray = bytearray(data_size)
        if data_bytes:
            self._data_mem[: len(data_bytes)] = data_bytes

        # persists across ticks so addr-compute and read/write ticks share it
        self.mem_addr: int = 0

        self._input: deque[int] = deque(input_tokens or [])
        self._output: list[int] = []

        self.alu_out: int = 0
        self.zero: bool = False
        self.lt_signed: bool = False
        self.mem_out: int = 0
        self.io_in: int = 0
        self.halt_req: bool = False

    def fetch_instr(self) -> int:
        """Read 4 bytes at PC from instruction memory, little-endian."""
        pc = self.pc
        if pc & 3:
            raise RuntimeError(f"PC misaligned: 0x{pc:08X}")
        if pc + 4 > len(self._inst_mem):
            raise RuntimeError(f"PC out of range: 0x{pc:08X}")
        return int.from_bytes(self._inst_mem[pc : pc + 4], "little")

    @property
    def opcode(self) -> int:
        return self.ir & 0x7F

    @property
    def rd(self) -> int:
        return (self.ir >> 7) & 0x1F

    @property
    def funct3(self) -> int:
        return (self.ir >> 12) & 0x07

    @property
    def rs1(self) -> int:
        return (self.ir >> 15) & 0x1F

    @property
    def rs2(self) -> int:
        return (self.ir >> 20) & 0x1F

    @property
    def funct7(self) -> int:
        return (self.ir >> 25) & 0x7F

    def reg_read(self, n: int) -> int:
        return 0 if n == 0 else self.regs[n]

    def reg_write(self, n: int, value: int) -> None:
        if n != 0:
            self.regs[n] = _u32(value)

    def imm(self) -> int:
        return decode_imm(self.ir)

    def alu_compute(self, op: int, a: int, b: int) -> None:
        """Run ALU; store result + flags. lt_signed uses sign-bit formula
        from microcode.md §1.1 — correct even when a−b overflows."""
        from src.micro.enums import AluOp

        a, b = _u32(a), _u32(b)

        if op == AluOp.NOP:
            self.alu_out = 0
            self.zero = False
            self.lt_signed = False
            return

        if op == AluOp.ADD:
            result = _u32(a + b)
        elif op == AluOp.SUB:
            result = _u32(a - b)
        elif op == AluOp.MUL:
            result = _u32(a * b)
        elif op == AluOp.SLL:
            result = _u32(a << (b & 0x1F))
        elif op == AluOp.SRL:
            result = (a >> (b & 0x1F)) & MASK32
        elif op == AluOp.AND:
            result = _u32(a & b)
        elif op == AluOp.OR:
            result = _u32(a | b)
        else:
            result = 0

        self.alu_out = result
        self.zero = result == 0
        a31, b31 = bool(a >> 31), bool(b >> 31)
        self.lt_signed = a31 if (a31 != b31) else bool(result >> 31)

    def mem_read_byte(self, addr: int) -> int:
        """Sign-extended byte read."""
        val = self._data_mem[addr] & 0xFF
        if val & 0x80:
            val |= ~0xFF
        return _u32(val)

    def mem_read_word(self, addr: int) -> int:
        return int.from_bytes(self._data_mem[addr : addr + 4], "little")

    def mem_write_byte(self, addr: int, value: int) -> None:
        self._data_mem[addr] = value & 0xFF

    def mem_write_word(self, addr: int, value: int) -> None:
        self._data_mem[addr : addr + 4] = _u32(value).to_bytes(4, "little")

    def data_mem_raw(self) -> bytearray:
        return self._data_mem

    def io_read(self, port: int) -> None:
        """Pop one token from input FIFO; set halt_req if empty."""
        if not self._input:
            self.halt_req = True
            return
        self.io_in = self._input.popleft() & 0xFF

    def io_write(self, port: int, value: int) -> None:
        self._output.append(value & 0xFF)

    @property
    def output_bytes(self) -> bytes:
        return bytes(self._output)

    @property
    def output_str(self) -> str:
        return self.output_bytes.decode("latin-1", errors="replace")
