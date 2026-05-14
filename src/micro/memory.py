from enum import IntEnum


class memory_mode(IntEnum):
    BYTE = 1
    WORD = 4


class data_memory:
    def __init__(self, size: int) -> None:
        self.size = size
        self.storage = [0] * size

    def read_memory(self, address: int, mode: memory_mode) -> int:
        if address < 0 or address + mode.value > self.size:
            raise ValueError(f"Wrong address: {address}")
        match mode:
            case memory_mode.BYTE:
                return self.storage[address] & 0xFF
            case memory_mode.WORD:
                res =  self.storage[address] & 0xFF
                res |= (self.storage[address + 1] & 0xFF) << 8
                res |= (self.storage[address + 2] & 0xFF) << 16
                res |= (self.storage[address + 3] & 0xFF) << 24
                return res

    def write(self, address: int, value: int, mode: memory_mode) -> None:
        if address < 0 or (address + mode.value) > self.size:
            raise ValueError(f"Wrong address: {address}")
        match mode:
            case memory_mode.BYTE:
                self.storage[address] = value & 0xFF
            case memory_mode.WORD:
                self.storage[address] = value & 0xFF
                self.storage[address + 1] = (value >> 8) & 0xFF
                self.storage[address + 2] = (value >> 16) & 0xFF
                self.storage[address + 3] = (value >> 24) & 0xFF


class instruction_memory:
    def __init__(self, size: int) -> None:
        self.size = size
        self.storage = [0] * size


    def load_from_bytes(self, bytes: bytes) -> None:
        size = len(bytes)
        if size > self.size:
            raise ValueError(f"Not enought memory: {self.size}, required: {size}")
        self.storage = list(bytes)


    def fetch(self, counter: int) -> int:
        if counter < 0 or counter + 4 > self.size:
            raise ValueError(f"Wrong counter: {counter}")
        if counter % 4 != 0:
            raise ValueError(f"Counter must be 4-signed: {counter}")
        res = self.storage[counter]
        res |= self.storage[counter + 1] << 8
        res |= self.storage[counter + 2] << 16
        res |= self.storage[counter + 3] << 24
        return res
