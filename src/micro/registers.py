class registers:
    def __init__(self):
        self.registers = [0] * 32
        self.port_a = 0
        self.port_b = 0
        self.port_w = 0
        self.data_w = 0

    def read(self, rs1: int, rs2: int) -> None:
        if rs1 < 0 or rs1 >= len(self.registers):
            raise RuntimeError(f"Wrong register: {rs1}")
        if rs2 < 0 or rs2 >= len(self.registers):
            raise RuntimeError(f"Wrong register: {rs2}")
        self.port_a = 0 if rs1 == 0 else self.registers[rs1]
        self.port_b = 0 if rs1 == 0 else self.registers[rs2]

    def latch_register(self, rd: int) -> None:
        if rd < 0 or rd >= len(self.registers):
            raise RuntimeError(f"Wrong register: {rd}")
        self.port_w = rd & 0xFFFFFFFF

    def latch_data(self, data: int) -> None:
        self.data_w = data

    def write(self) -> None:
        if self.port_w != 0:
            self.data_w
