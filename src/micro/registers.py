from src.micro.line import line
from src.micro.tick import need_tick

class registers(need_tick):
    def __init__(self, line_a: line, line_b: line) -> None:
        self.registers: list[int] = [0] * 32
        self.line_a: line = line_a
        self.line_b: line = line_b
        self.port_w: int = 0
        self.data_w: int = 0

    def latch_and_write_port_a(self, regis_source1) -> None:
        data_a: int = 0 if regis_source1 == 0 else self.registers[regis_source1 & 0x1F]
        self.line_a.send_value(data_a)

    def latch_and_write_port_b(self, regis_source2) -> None:
        data_b: int = 0 if regis_source2 == 0 else self.registers[regis_source2 & 0x1F]
        self.line_b.send_value(data_b)

    def latch_port_w(self, regis_dest: int) -> None:
        value: int = regis_dest & 0x1F
        self.port_w = value

    def latch_data_w(self, to_write: int) -> None:
        value: int = to_write & 0xFFFFFFFF
        self.data_w = value

    def tick(self) -> None:
        if self.port_w != 0:
            self.registers[self.port_w] = self.data_w
