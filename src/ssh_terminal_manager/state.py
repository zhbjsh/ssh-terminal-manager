from __future__ import annotations

from typing import TYPE_CHECKING

from terminal_manager import Event

if TYPE_CHECKING:
    from .manager import SSHManager

STATE_NAMES = ["online", "connected", "error"]


class State:
    online: bool = False
    connected: bool = False
    error: bool = False

    def __init__(self, manager: SSHManager) -> None:
        self._manager = manager
        self.on_change = Event()

    def __setattr__(self, name, value):
        prev_value = getattr(self, name, None)
        super().__setattr__(name, value)

        if name not in STATE_NAMES or value == prev_value:
            return

        self._manager.logger.debug(
            "%s: state.%s => %s",
            self._manager.name,
            name,
            value,
        )
        self.on_change.notify(self)

    def handle_ping_error(self) -> None:
        self.online = False

    def handle_ping_success(self) -> None:
        self.online = True

    def handle_auth_error(self) -> None:
        self._manager.reset_commands()
        self.error = True

    def handle_connect_error(self) -> None:
        self._manager.reset_commands()

    def handle_connect_success(self) -> None:
        self.connected = True
        self.error = False

    def handle_disconnect(self) -> None:
        self.connected = False

    def handle_execute_error(self) -> None:
        self._manager.reset_commands()
