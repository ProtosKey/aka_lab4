from enum import IntEnum


class arithmetic_enum(IntEnum):
    ADD = 0b000001
    SUB = 0b000010
    SHL = 0b000100
    SHR = 0b001000
    AND = 0b010000
    OR  = 0b100000


class arithmetic:
    def __init__(self) -> None:
        self.port_a = 0
        self.port_b = 0
        self.bus_out = 0

    def latch_latch_register(self, a: int, b: int) -> None:
        self.port_a = a
        self.port_b = b

    def calc_by_signals(self, op_signals) -> None:
        if op_signals & arithmetic_enum.ADD:
            self.bus_out = self.port_a + self.port_b
        elif op_signals & arithmetic_enum.SUB:
            self.bus_out = self.port_a - self.port_b
        elif op_signals & arithmetic_enum.SHL:
            self.bus_out = self.port_a << self.port_b
        elif op_signals & arithmetic_enum.SHR:
            self.bus_out = self.port_a >> self.port_b
        elif op_signals & arithmetic_enum.AND:
            self.bus_out = self.port_a & self.port_b
        elif op_signals & arithmetic_enum.OR:
            self.bus_out = self.port_a | self.port_b

        self.bus_out &= 0xFFFFFFFF
