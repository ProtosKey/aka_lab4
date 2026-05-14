class registers:
    def __init__(self):
        self.registers = [0] * 32

    def read(self, register: int) -> int:
        if register < 0 or register >= len(self.registers):
            raise ValueError(f"Wrong register: {register}")
        return self.registers[register]

    def write(self, register: int, value: int) -> None:
        if register < 0 or register >= len(self.registers):
            raise ValueError(f"Wrong register: {register}")
        if register == 0:
            return
        self.registers[register] = value & 0xFFFFFFFF
