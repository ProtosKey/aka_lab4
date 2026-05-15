from abc import ABC, abstractmethod


class need_tick(ABC):
    @abstractmethod
    def tick(self) -> None:
        pass

class need_op_signal(ABC):
    @abstractmethod
    def do_by_signal_op(self, op: int) -> None:
        pass
