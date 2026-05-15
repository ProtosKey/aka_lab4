from enum import IntEnum
from src.micro.line import line
from src.micro.tick import need_op_signal


class arithmetic_op(IntEnum):
    ADD = 0b000001
    SUB = 0b000010
    SHL = 0b000100
    SHR = 0b001000
    AND = 0b010000
    OR  = 0b100000
    NUL = 0b000000


class arithmetic(need_op_signal):
    def __init__(self, line_out: line) -> None:
        self.port_a: int = 0
        self.port_b: int = 0
        self.op = arithmetic_op.NUL
        self.line_out: line = line_out

    def latch_port_a(self, value: int) -> None:
        self.port_a = value

    def latch_port_b(self, value: int) -> None:
        self.port_b = value

    def do_by_signal_op(self, op: int) -> None:
        value_to_send = 0
        if op & arithmetic_op.ADD:
            value_to_send = self.port_a + self.port_b
        elif op & arithmetic_op.SUB:
            value_to_send = self.port_a - self.port_b
        elif op & arithmetic_op.SHL:
            value_to_send = self.port_a << self.remove_for_shift(self.port_b)
        elif op & arithmetic_op.SHR:
            value_to_send = self.port_a >> self.remove_for_shift(self.port_b)
        elif op & arithmetic_op.AND:
            value_to_send = self.port_a & self.port_b
        elif op & arithmetic_op.OR:
            value_to_send = self.port_a | self.port_b
        else:
            return
        self.line_out.send_value(self.remove_more_that(value_to_send))

    def remove_for_shift(self, to_remove: int) -> int:
        return to_remove & 0x1F

    def remove_more_that(self, to_remove: int) -> int:
        return to_remove & 0xFFFFFFFF
