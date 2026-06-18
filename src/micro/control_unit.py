"""
Microcoded Control Unit (mc variant).

Per tick the CU:
  1. Reads the micro-instruction at µPC from the microcode ROM.
  2. Fetches the current instruction from IM[PC] (combinational).
  3. Drives all combinational signals on the datapath.
  4. Commits state changes on the tick edge in this order:
       IR, regs[rd], PC, memory write, I/O output, mem_addr latch
  5. Emits a TickTrace describing state changes that actually fired.
  6. Advances µPC via the SEQ field.

Returns None from step() when clock is permanently stopped.

Trace format (timing.md §1.1):
  tick=N PC=<hex32> IR=<hex32> µPC=<hex8> | <event>...

Events emitted only when the corresponding state actually changes:
  IR<=<hex32>           when IR_WE=1
  regs[n]<=<hex32>      when REGS_WE=1 and rd != 0
  PC<=<hex32>           when PC_WE=1
  M1[addr]<=<byte>      byte store
  M4[addr]<=<word>      word store
  IN  port=p, value=hh  IN instruction (port 0)
  OUT port=p, value=hh  OUT instruction (port 1)
  BRANCH taken=<0|1>    alongside PC<= for B-type
  data_mem.addr<=<hex>  address latch update on addr-compute ticks (SEQ=NEXT)
  µPC<=<hex8>           always, except HALT ticks where µPC is frozen
  HALT reason=<why>     on HALT or IN-empty
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.micro.data_path import DataPath, _u32
from src.micro.enums import AluOp, IoOp, MemOp, PcSrc, Seq, WbSel
from src.micro.microcode_rom import MICROCODE_ROM, decode

_HALTED = -1  # sentinel for a stopped clock


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
    """Microcoded Control Unit; state = µPC."""

    def __init__(self, dp: DataPath) -> None:
        self.dp: DataPath = dp
        self.mpc: int = 0
        self._tick: int = 0

    # ─────────────────────────────────────────────────────────────────────

    def step(self) -> TickTrace | None:
        """Execute one clock tick.  Returns None if clock is stopped."""
        if self.mpc is _HALTED:
            return None

        self._tick += 1
        mi = MICROCODE_ROM[self.mpc]

        # Snapshot state-before for the trace header
        trace = TickTrace(
            tick=self._tick,
            pc=self.dp.pc,
            ir=self.dp.ir,
            mpc=self.mpc,
        )

        # ── 1. Combinational: fetch instruction from IM ───────────────────
        new_instr = self.dp.fetch_instr()

        # ── 2. Combinational: read source registers (from latched IR) ─────
        rs1_val = self.dp.reg_read(self.dp.rs1)
        rs2_val = self.dp.reg_read(self.dp.rs2)

        # ── 3. Combinational: ALU B-operand mux ──────────────────────────
        port_b = self.dp.imm() if mi.is_imm else rs2_val

        # ── 4. Combinational: ALU ─────────────────────────────────────────
        if mi.alu_op != AluOp.NOP:
            self.dp.alu_compute(mi.alu_op, rs1_val, port_b)

        # ── 5. Combinational: data-memory read ────────────────────────────
        if mi.mem_op == MemOp.RD_B:
            self.dp.mem_out = self.dp.mem_read_byte(self.dp.mem_addr)
        elif mi.mem_op == MemOp.RD_W:
            self.dp.mem_out = self.dp.mem_read_word(self.dp.mem_addr)

        # ── 6. Combinational: I/O IN (may set halt_req) ───────────────────
        io_in_val = 0
        io_port_in = self.dp.imm() & 0xFFF  # port number from imm
        if mi.io_op == IoOp.IN:
            self.dp.io_read(io_port_in)
            if self.dp.halt_req:
                # Empty input FIFO: freeze, no state updates
                trace.events.append("HALT reason=in-empty")
                trace.halted = True
                trace.halt_reason = "in-empty"
                self.mpc = _HALTED
                return trace
            io_in_val = self.dp.io_in

        # ── 7. Combinational: write-back mux ──────────────────────────────
        pc4 = _u32(self.dp.pc + 4)
        imm_hi = _u32(self.dp.ir & 0xFFFFF000)  # LUI: IR[31:12] in place

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

        # ── 8. Combinational: PC mux ──────────────────────────────────────
        pc_imm = _u32(self.dp.pc + self.dp.imm())
        alu_jalr = _u32(self.dp.alu_out & 0xFFFF_FFFE)  # & ~1

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

        # ── COMMIT: state changes on tick edge ────────────────────────────

        # (a) IR latch
        if mi.ir_we:
            self.dp.ir = new_instr
            trace.events.append(f"IR<={new_instr:08X}")

        # (b) Register file write  [before PC so trace matches timing.md]
        if mi.regs_we:
            rd = self.dp.rd  # from already-latched IR (execute ticks only)
            if rd != 0:
                self.dp.reg_write(rd, data_w)
                trace.events.append(f"regs[{rd}]<={data_w:08X}")

        # (c) PC update
        if mi.pc_we:
            self.dp.pc = next_pc
            trace.events.append(f"PC<={next_pc:08X}")

        # (d) Memory write
        if mi.mem_op == MemOp.WR_B:
            addr = self.dp.mem_addr
            self.dp.mem_write_byte(addr, rs2_val)
            trace.events.append(f"M1[{addr:08X}]<={rs2_val & 0xFF:02X}")
        elif mi.mem_op == MemOp.WR_W:
            addr = self.dp.mem_addr
            self.dp.mem_write_word(addr, rs2_val)
            trace.events.append(f"M4[{addr:08X}]<={rs2_val & 0xFFFF_FFFF:08X}")

        # (e) I/O port write
        if mi.io_op == IoOp.OUT:
            io_port_out = self.dp.imm() & 0xFFF
            byte_val = rs1_val & 0xFF
            self.dp.io_write(io_port_out, byte_val)
            trace.events.append(f"OUT port={io_port_out}, value={byte_val:02X}")

        if mi.io_op == IoOp.IN:
            trace.events.append(f"IN port={io_port_in}, value={io_in_val:02X}")

        # (f) Branch annotation
        if mi.pc_src in (PcSrc.BR_EQ, PcSrc.BR_NE, PcSrc.BR_LT, PcSrc.BR_GE):
            taken = next_pc == pc_imm
            trace.events.append(f"BRANCH taken={int(taken)}")

        # (g) mem_addr latch — update whenever ALU ran
        if mi.alu_op != AluOp.NOP:
            self.dp.mem_addr = self.dp.alu_out
            if mi.seq == Seq.NEXT:
                # Addr-compute tick: show the latch update in the trace
                trace.events.append(f"data_mem.addr<={self.dp.alu_out:08X}")

        # ── µPC sequencer ────────────────────────────────────────────────
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
