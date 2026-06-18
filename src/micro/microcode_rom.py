from dataclasses import dataclass

from src.micro.enums import AluOp, IoOp, MemOp, PcSrc, Seq, WbSel


@dataclass(frozen=True)
class MicroInstruction:
    ir_we: int
    pc_we: int
    regs_we: int
    is_imm: int
    alu_op: AluOp
    mem_op: MemOp
    io_op: IoOp
    wb_sel: WbSel
    pc_src: PcSrc
    seq: Seq

    def pack(self) -> int:
        w = 0
        w |= self.ir_we
        w |= self.pc_we << 1
        w |= self.regs_we << 2
        w |= self.is_imm << 3
        w |= int(self.alu_op) << 4
        w |= int(self.mem_op) << 7
        w |= int(self.io_op) << 10
        w |= int(self.wb_sel) << 12
        w |= int(self.pc_src) << 15
        w |= int(self.seq) << 18
        return w

    @classmethod
    def unpack(cls, word: int) -> "MicroInstruction":
        return cls(
            ir_we=(word >> 0) & 0x1,
            pc_we=(word >> 1) & 0x1,
            regs_we=(word >> 2) & 0x1,
            is_imm=(word >> 3) & 0x1,
            alu_op=AluOp((word >> 4) & 0x7),
            mem_op=MemOp((word >> 7) & 0x7),
            io_op=IoOp((word >> 10) & 0x3),
            wb_sel=WbSel((word >> 12) & 0x7),
            pc_src=PcSrc((word >> 15) & 0x7),
            seq=Seq((word >> 18) & 0x3),
        )


def _mi(
    ir_we: int = 0,
    pc_we: int = 0,
    regs_we: int = 0,
    is_imm: int = 0,
    alu_op: AluOp = AluOp.NOP,
    mem_op: MemOp = MemOp.NONE,
    io_op: IoOp = IoOp.NONE,
    wb_sel: WbSel = WbSel.NONE,
    pc_src: PcSrc = PcSrc.PC4,
    seq: Seq = Seq.FETCH,
) -> MicroInstruction:
    return MicroInstruction(
        ir_we, pc_we, regs_we, is_imm, alu_op, mem_op, io_op, wb_sel, pc_src, seq
    )


MICROCODE_ROM: list[MicroInstruction] = [
    # 0x00  µFETCH
    _mi(ir_we=1, seq=Seq.DECODE),
    # 0x01  µADD
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.ADD, wb_sel=WbSel.ALU),
    # 0x02  µSUB
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.SUB, wb_sel=WbSel.ALU),
    # 0x03  µMUL
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.MUL, wb_sel=WbSel.ALU),
    # 0x04  µSLL
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.SLL, wb_sel=WbSel.ALU),
    # 0x05  µSRL
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.SRL, wb_sel=WbSel.ALU),
    # 0x06  µAND
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.AND, wb_sel=WbSel.ALU),
    # 0x07  µOR
    _mi(pc_we=1, regs_we=1, alu_op=AluOp.OR, wb_sel=WbSel.ALU),
    # 0x08  µADDI
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.ADD, wb_sel=WbSel.ALU),
    # 0x09  µANDI
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.AND, wb_sel=WbSel.ALU),
    # 0x0A  µORI
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.OR, wb_sel=WbSel.ALU),
    # 0x0B  µSLLI
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.SLL, wb_sel=WbSel.ALU),
    # 0x0C  µSRLI
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.SRL, wb_sel=WbSel.ALU),
    # 0x0D  µLB.addr
    _mi(is_imm=1, alu_op=AluOp.ADD, seq=Seq.NEXT),
    # 0x0E  µLB.read
    _mi(pc_we=1, regs_we=1, mem_op=MemOp.RD_B, wb_sel=WbSel.MEM),
    # 0x0F  µLW.addr
    _mi(is_imm=1, alu_op=AluOp.ADD, seq=Seq.NEXT),
    # 0x10  µLW.read
    _mi(pc_we=1, regs_we=1, mem_op=MemOp.RD_W, wb_sel=WbSel.MEM),
    # 0x11  µSB.addr
    _mi(is_imm=1, alu_op=AluOp.ADD, seq=Seq.NEXT),
    # 0x12  µSB.write
    _mi(pc_we=1, mem_op=MemOp.WR_B),
    # 0x13  µSW.addr
    _mi(is_imm=1, alu_op=AluOp.ADD, seq=Seq.NEXT),
    # 0x14  µSW.write
    _mi(pc_we=1, mem_op=MemOp.WR_W),
    # 0x15  µBEQ
    _mi(pc_we=1, alu_op=AluOp.SUB, pc_src=PcSrc.BR_EQ),
    # 0x16  µBNE
    _mi(pc_we=1, alu_op=AluOp.SUB, pc_src=PcSrc.BR_NE),
    # 0x17  µBLT
    _mi(pc_we=1, alu_op=AluOp.SUB, pc_src=PcSrc.BR_LT),
    # 0x18  µBGE
    _mi(pc_we=1, alu_op=AluOp.SUB, pc_src=PcSrc.BR_GE),
    # 0x19  µJAL
    _mi(pc_we=1, regs_we=1, wb_sel=WbSel.PC4, pc_src=PcSrc.PC_IMM),
    # 0x1A  µJALR
    _mi(pc_we=1, regs_we=1, is_imm=1, alu_op=AluOp.ADD, wb_sel=WbSel.PC4, pc_src=PcSrc.ALU),
    # 0x1B  µLUI
    _mi(pc_we=1, regs_we=1, wb_sel=WbSel.IMM_HI),
    # 0x1C  µIN
    _mi(pc_we=1, regs_we=1, io_op=IoOp.IN, wb_sel=WbSel.IO_IN),
    # 0x1D  µOUT
    _mi(pc_we=1, io_op=IoOp.OUT),
    # 0x1E  µHALT
    _mi(seq=Seq.HALT),
]

assert len(MICROCODE_ROM) == 0x1F, f"ROM has {len(MICROCODE_ROM)} entries, expected 31"


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

_DECODE_TABLE: dict[tuple[int, int | None, int | None], int] = {
    (_OP, 0b000, 0b0000000): 0x01,  # ADD
    (_OP, 0b000, 0b0100000): 0x02,  # SUB
    (_OP, 0b000, 0b0000001): 0x03,  # MUL
    (_OP, 0b001, 0b0000000): 0x04,  # SLL
    (_OP, 0b101, 0b0000000): 0x05,  # SRL
    (_OP, 0b111, 0b0000000): 0x06,  # AND
    (_OP, 0b110, 0b0000000): 0x07,  # OR
    (_OP_IMM, 0b000, None): 0x08,  # ADDI
    (_OP_IMM, 0b111, None): 0x09,  # ANDI
    (_OP_IMM, 0b110, None): 0x0A,  # ORI
    (_OP_IMM, 0b001, None): 0x0B,  # SLLI
    (_OP_IMM, 0b101, None): 0x0C,  # SRLI
    (_LOAD, 0b000, None): 0x0D,  # LB
    (_LOAD, 0b010, None): 0x0F,  # LW
    (_STORE, 0b000, None): 0x11,  # SB
    (_STORE, 0b010, None): 0x13,  # SW
    (_BRANCH, 0b000, None): 0x15,  # BEQ
    (_BRANCH, 0b001, None): 0x16,  # BNE
    (_BRANCH, 0b100, None): 0x17,  # BLT
    (_BRANCH, 0b101, None): 0x18,  # BGE
    (_JAL, None, None): 0x19,  # JAL
    (_JALR, 0b000, None): 0x1A,  # JALR
    (_LUI, None, None): 0x1B,  # LUI
    (_IO_IN, 0b000, None): 0x1C,  # IN
    (_IO_OUT, 0b000, None): 0x1D,  # OUT
    (_SYSTEM, 0b000, None): 0x1E,  # HALT
}


def decode(opcode: int, funct3: int, funct7: int) -> int:
    key = (opcode, funct3, funct7)
    if key in _DECODE_TABLE:
        return _DECODE_TABLE[key]
    key2 = (opcode, funct3, None)
    if key2 in _DECODE_TABLE:
        return _DECODE_TABLE[key2]
    key3 = (opcode, None, None)
    if key3 in _DECODE_TABLE:
        return _DECODE_TABLE[key3]
    return 0x1E
