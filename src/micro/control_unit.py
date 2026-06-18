"""Microcoded Control Unit: one step() call = one clock tick."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.micro.data_path import DataPath, _u32
from src.micro.enums import AluOp, IoOp, MemOp, PcSrc, Seq, WbSel
from src.micro.microcode_rom import MICROCODE_ROM, decode

_HALTED = -1


@dataclass
class TickTrace:
    tick: int
    pc: int
    ir: int
    mpc: int
    events: list[str] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""

    def format(self) -> str:
        prefix = f"tick={self.tick} PC={self.pc:08X} IR={self.ir:08X} µPC={self.mpc:02X}"
        if self.events:
            return prefix + " | " + " ".join(self.events)
        return prefix


class ControlUnit:
    """Microcoded CU; only state is µPC."""

    def __init__(self, dp: DataPath) -> None:
        self.dp: DataPath = dp
        self.mpc: int = 0
        self._tick: int = 0

    def step(self) -> TickTrace | None:
        """Execute one clock tick. Returns None when stopped."""
        if self.mpc is _HALTED:
            return None

        self._tick += 1
        mi = MICROCODE_ROM[self.mpc]
        trace = TickTrace(tick=self._tick, pc=self.dp.pc, ir=self.dp.ir, mpc=self.mpc)

        # combinational phase
        new_instr = self.dp.fetch_instr()
        rs1_val = self.dp.reg_read(self.dp.rs1)
        rs2_val = self.dp.reg_read(self.dp.rs2)
        port_b = self.dp.imm() if mi.is_imm else rs2_val

        if mi.alu_op != AluOp.NOP:
            self.dp.alu_compute(mi.alu_op, rs1_val, port_b)

        if mi.mem_op == MemOp.RD_B:
            self.dp.mem_out = self.dp.mem_read_byte(self.dp.mem_addr)
        elif mi.mem_op == MemOp.RD_W:
            self.dp.mem_out = self.dp.mem_read_word(self.dp.mem_addr)

        io_in_val = 0
        io_port_in = self.dp.imm() & 0xFFF
        if mi.io_op == IoOp.IN:
            self.dp.io_read(io_port_in)
            if self.dp.halt_req:
                trace.events.append("HALT reason=in-empty")
                trace.halted = True
                trace.halt_reason = "in-empty"
                self.mpc = _HALTED
                return trace
            io_in_val = self.dp.io_in

        pc4 = _u32(self.dp.pc + 4)
        imm_hi = _u32(self.dp.ir & 0xFFFFF000)

        if mi.wb_sel == WbSel.ALU:
            data_w = self.dp.alu_out
        elif mi.wb_sel == WbSel.MEM:
            data_w = self.dp.mem_out
        elif mi.wb_sel == WbSel.PC4:
            data_w = pc4
        elif mi.wb_sel == WbSel.IMM_HI:
            data_w = imm_hi
        elif mi.wb_sel == WbSel.IO_IN:
            data_w = io_in_val
        else:
            data_w = 0

        pc_imm = _u32(self.dp.pc + self.dp.imm())
        alu_jalr = _u32(self.dp.alu_out & 0xFFFF_FFFE)

        if mi.pc_src == PcSrc.PC4:
            next_pc = pc4
        elif mi.pc_src == PcSrc.PC_IMM:
            next_pc = pc_imm
        elif mi.pc_src == PcSrc.ALU:
            next_pc = alu_jalr
        elif mi.pc_src == PcSrc.BR_EQ:
            next_pc = pc_imm if self.dp.zero else pc4
        elif mi.pc_src == PcSrc.BR_NE:
            next_pc = pc_imm if not self.dp.zero else pc4
        elif mi.pc_src == PcSrc.BR_LT:
            next_pc = pc_imm if self.dp.lt_signed else pc4
        elif mi.pc_src == PcSrc.BR_GE:
            next_pc = pc4 if self.dp.lt_signed else pc_imm
        else:
            next_pc = pc4

        # commit — order matters for trace correctness
        if mi.ir_we:
            self.dp.ir = new_instr
            trace.events.append(f"IR<={new_instr:08X}")

        if mi.regs_we:
            rd = self.dp.rd
            if rd != 0:
                self.dp.reg_write(rd, data_w)
                trace.events.append(f"regs[{rd}]<={data_w:08X}")

        if mi.pc_we:
            self.dp.pc = next_pc
            trace.events.append(f"PC<={next_pc:08X}")

        if mi.mem_op == MemOp.WR_B:
            addr = self.dp.mem_addr
            self.dp.mem_write_byte(addr, rs2_val)
            trace.events.append(f"M1[{addr:08X}]<={rs2_val & 0xFF:02X}")
        elif mi.mem_op == MemOp.WR_W:
            addr = self.dp.mem_addr
            self.dp.mem_write_word(addr, rs2_val)
            trace.events.append(f"M4[{addr:08X}]<={rs2_val & 0xFFFF_FFFF:08X}")

        if mi.io_op == IoOp.OUT:
            io_port_out = self.dp.imm() & 0xFFF
            byte_val = rs1_val & 0xFF
            self.dp.io_write(io_port_out, byte_val)
            trace.events.append(f"OUT port={io_port_out}, value={byte_val:02X}")

        if mi.io_op == IoOp.IN:
            trace.events.append(f"IN port={io_port_in}, value={io_in_val:02X}")

        if mi.pc_src in (PcSrc.BR_EQ, PcSrc.BR_NE, PcSrc.BR_LT, PcSrc.BR_GE):
            trace.events.append(f"BRANCH taken={int(next_pc == pc_imm)}")

        if mi.alu_op != AluOp.NOP:
            self.dp.mem_addr = self.dp.alu_out
            if mi.seq == Seq.NEXT:
                trace.events.append(f"data_mem.addr<={self.dp.alu_out:08X}")

        # µPC sequencer
        if mi.seq == Seq.NEXT:
            next_mpc = self.mpc + 1
        elif mi.seq == Seq.FETCH:
            next_mpc = 0x00
        elif mi.seq == Seq.DECODE:
            next_mpc = decode(
                new_instr & 0x7F,
                (new_instr >> 12) & 0x7,
                (new_instr >> 25) & 0x7F,
            )
        else:  # Seq.HALT
            trace.events.append("HALT reason=halt")
            trace.halted = True
            trace.halt_reason = "halt"
            self.mpc = _HALTED
            return trace

        self.mpc = next_mpc
        trace.events.append(f"µPC<={next_mpc:02X}")
        return trace
