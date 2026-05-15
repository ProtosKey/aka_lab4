from enum import IntEnum
from src.micro.tick import need_op_signal, need_tick
from src.micro.line import line


class memory_op(IntEnum):
    READ_BYTE = 0b0001
    READ_WORD = 0b0010
    WRITE_BYTE = 0b0100
    WRITE_WORD = 0b1000
    NUL = 0b0000


class data_memory(need_tick, need_op_signal):
    def __init__(self, size: int, line_out: line) -> None:
        self.size: int = size
        self.line_out: line = line_out
        self.storage: list[int] = [0] * size
        self.port_addr: int = 0
        self.port_data: int = 0
        self.write_en: bool = False
        self.current_op: int = memory_op.NUL

    def latch_addr(self, address: int) -> None:
        self.port_addr = address

    def latch_data(self, value: int) -> None:
        self.port_data = value

    def do_by_signal_op(self, op: int) -> None:
        self.current_op = op
        if op & memory_op.READ_BYTE:
            val = self.remove_not_byte(self.storage[self.port_addr])
            self.line_out.send_value(val)
        elif op & memory_op.READ_WORD:
            res =  self.storage[self.port_addr] & 0xFF
            res |= self.remove_not_byte(self.storage[self.port_addr + 1]) << 8
            res |= self.remove_not_byte(self.storage[self.port_addr + 2]) << 16
            res |= self.remove_not_byte(self.storage[self.port_addr + 3]) << 24
            self.line_out.send_value(res)

    def remove_not_byte(self, to_remove: int) -> int:
        return to_remove & 0xFF

    def tick(self) -> None:
        if self.current_op & memory_op.WRITE_BYTE:
            self.storage[self.port_addr] = self.remove_not_byte(self.port_data)
        elif self.current_op & memory_op.WRITE_WORD:
            self.storage[self.port_addr] = self.remove_not_byte(self.port_data)
            self.storage[self.port_addr + 1] = self.remove_not_byte(self.port_data >> 8)
            self.storage[self.port_addr + 2] = self.remove_not_byte(self.port_data >> 16)
            self.storage[self.port_addr + 3] = self.remove_not_byte(self.port_data >> 24)
        self.current_op = memory_op.NUL


class instruction_memory:
    def __init__(self, size: int, line_out: line) -> None:
        self.size = size
        self.storage = [0] * size
        self.line_out = line_out

    def load_from_bytes(self, bytes: bytes) -> None:
        size = len(bytes)
        if size > self.size:
            raise ValueError(f"Not enought memory: {self.size}, required: {size}")
        self.storage = list(bytes)

    def fetch_by_address(self, prog_counter: int) -> None:
        if prog_counter % 4 != 0:
            raise ValueError("Instruction address must be 4-byte aligned")
        res = self.remove_not_byte(self.storage[prog_counter])
        res |= self.remove_not_byte(self.storage[prog_counter + 1]) << 8
        res |= self.remove_not_byte(self.storage[prog_counter + 2]) << 16
        res |= self.remove_not_byte(self.storage[prog_counter + 3]) << 24
        self.line_out.send_value(res)

    def remove_not_byte(self, to_remove: int) -> int:
        return to_remove & 0xFF
