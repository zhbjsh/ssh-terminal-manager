from logging import Logger
from terminal_manager import Event

ONLINE = "online"
CONNECTED = "connected"
ERROR = "error"


class State:
    online: bool = False
    connected: bool = False
    error: bool = False

    def __init__(self, name: str, logger: Logger) -> None:
        self._name = name
        self._logger = logger
        self.on_change = Event()

    def update(self, name, value) -> None:
        if getattr(self, name) == value:
            return

        setattr(self, name, value)
        self._logger.debug("%s: state.%s => %s", self._name, name, value)
        self.on_change.notify(self)
