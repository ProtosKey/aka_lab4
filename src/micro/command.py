from dataclasses import dataclass
from abc import ABC, abstractmethod

class instruction(ABC):
    @abstractmethod
    def pack(self) -> int:
        return -1


@dataclass
class type_b(instruction):
    opcode: int
    funct3: int
    source1: int
    source2: int
    immediate: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.funct3 & 0x7) << 12
        res |= (self.source1 & 0x1F) << 15
        res |= (self.source2 & 0x1F) << 20

        imm = self.immediate
        res |= ((imm >> 11) & 0x1) << 7
        res |= ((imm >> 1) & 0xF) << 8
        res |= ((imm >> 5) & 0x3F) << 25
        res |= ((imm >> 12) & 0x1) << 31
        return res


@dataclass
class type_j(instruction):
    opcode: int
    destination: int
    immediate: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.destination & 0x1F) << 7

        imm = self.immediate
        res |= ((imm >> 12) & 0xFF) << 12
        res |= ((imm >> 11) & 0x1) << 20
        res |= ((imm >> 1) & 0x3FF) << 21
        res |= ((imm >> 20) & 0x1) << 31
        return res


@dataclass
class type_s(instruction):
    opcode: int
    funct3: int
    source1: int
    source2: int
    immediate: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.immediate & 0x1F) << 7
        res |= (self.funct3 & 0x7) << 12
        res |= (self.source1 & 0x1F) << 15
        res |= (self.source2 & 0x1F) << 20
        res |= ((self.immediate >> 5) & 0x7F) << 25
        return res


@dataclass
class type_i(instruction):
    opcode: int
    destination: int
    funct3: int
    source1: int
    immediate: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.destination & 0x1F) << 7
        res |= (self.funct3 & 0x7) << 12
        res |= (self.source1 & 0x1F) << 15
        res |= (self.immediate & 0xFFF) << 20
        return res


@dataclass
class type_u(instruction):
    opcode: int
    destination: int
    data: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.destination & 0x1F) << 7
        res |= (self.data & 0xFFFFF) << 12
        return res


@dataclass
class type_r(instruction):
    opcode: int
    destination: int
    funct3: int
    source1: int
    source2: int
    funct7: int

    def pack(self) -> int:
        res = 0
        res |= (self.opcode & 0x7F)
        res |= (self.destination & 0x1F) << 7
        res |= (self.funct3 & 0x7) << 12
        res |= (self.source1 & 0x1F) << 15
        res |= (self.source2 & 0x1F) << 20
        res |= (self.funct7 & 0x7F) << 25
        return res
