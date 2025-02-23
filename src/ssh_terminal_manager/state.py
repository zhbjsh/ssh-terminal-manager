from __future__ import annotations

from enum import StrEnum
from time import time
from typing import TYPE_CHECKING

from terminal_manager import Event

if TYPE_CHECKING:
    from .manager import SSHManager

STATE_NAMES = ["online", "connected", "request", "error"]
TIMEOUTS = {"turn_on": 60, "turn_off": 30, "restart": 30, "connect": 30}


class Request(StrEnum):
    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    RESTART = "restart"
    CONNECT = "connect"


class State:
    online: bool = False
    connected: bool = False
    request: Request | None = None
    error: bool = False

    def __init__(self, manager: SSHManager) -> None:
        self._manager = manager
        self._request_timestamp = time()
        self.on_change = Event()

    def __setattr__(self, name, value):
        prev_value = getattr(self, name, None)
        super().__setattr__(name, value)

        if name not in STATE_NAMES or value == prev_value:
            return

        if name == "request":
            self._request_timestamp = time()

        self._manager.logger.debug(
            "%s: state.%s => %s",
            self._manager.name,
            name,
            value,
        )
        self.on_change.notify(self)

    def handle_update(self) -> None:
        if not self.request:
            return
        if time() - self._request_timestamp > TIMEOUTS[self.request]:
            self.request = None

    def handle_ping_error(self) -> None:
        if self.connected:
            self._manager.disconnect()
        if self.online:
            self._manager.reset_commands()
        if self.request == Request.TURN_OFF:
            self.request = None
        if self.request == Request.RESTART:
            self.request = Request.TURN_ON
        self.online = False

    def handle_ping_success(self) -> None:
        if self.request == Request.TURN_ON:
            self.request = Request.CONNECT
        self.online = True

    def handle_auth_error(self) -> None:
        self._manager.reset_commands()
        self.error = True

    def handle_connect_error(self) -> None:
        self._manager.reset_commands()

    def handle_connect_success(self) -> None:
        if self.request == Request.CONNECT:
            self.request = None
        self.connected = True
        self.error = False

    def handle_disconnect(self) -> None:
        self.connected = False

    def handle_execute_error(self) -> None:
        self._manager.reset_commands()

    def handle_turn_on(self) -> None:
        self.request = Request.TURN_ON

    def handle_turn_off(self) -> None:
        self.request = Request.TURN_OFF

    def handle_restart(self) -> None:
        self.request = Request.RESTART
