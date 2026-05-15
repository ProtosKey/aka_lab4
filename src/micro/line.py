class line:
    def __init__(self, name) -> None:
        self.value = 0
        self.name = name
        self.listeners = []

    def connect(self, after_send) -> None:
        self.listeners.append(after_send)

    def send_value(self, value) -> None:
        self.value = value
        for send_f in self.listeners:
            send_f(value)

    def __repr__(self) -> str:
        return f"line={self.name}, destinations={len(self.listeners)}"
