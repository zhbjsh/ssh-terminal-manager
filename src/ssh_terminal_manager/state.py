from logging import Logger

from terminal_manager import Event

STATE_NAMES = ["online", "connected", "error"]


class State:
    online: bool = False
    connected: bool = False
    error: bool = False

    def __init__(self, name: str, logger: Logger) -> None:
        self._name = name
        self._logger = logger
        self.on_change = Event()

    def __setattr__(self, name, value):
        prev_value = getattr(self, name, None)
        super().__setattr__(name, value)

        if name not in STATE_NAMES or value == prev_value:
            return

        self._logger.debug("%s: state.%s => %s", self._name, name, value)
        self.on_change.notify(self)
