from __future__ import annotations

import logging

from terminal_manager import (
    DEFAULT_ALLOW_TURN_OFF,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_DISCONNECT_MODE,
    DEFAULT_DISCONNECT_MODE_DELAY,
    DEFAULT_REQUEST_TIMEOUTS,
    Collection,
    Manager,
)
import wakeonlan

from .terminal import SSHTerminal

_LOGGER = logging.getLogger(__name__)


class SSHManager(Manager):
    _terminal: SSHTerminal

    def __init__(
        self,
        terminal: SSHTerminal,
        *,
        name: str | None = None,
        command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
        allow_turn_off: bool = DEFAULT_ALLOW_TURN_OFF,
        disconnect_mode: bool = DEFAULT_DISCONNECT_MODE,
        disconnect_mode_delay: int = DEFAULT_DISCONNECT_MODE_DELAY,
        request_timeouts: dict[str, int] = DEFAULT_REQUEST_TIMEOUTS,
        mac_address: str | None = None,
        collection: Collection | None = None,
        logger: logging.Logger = _LOGGER,
    ) -> None:
        super().__init__(
            terminal,
            name=name or terminal.host,
            command_timeout=command_timeout,
            allow_turn_off=allow_turn_off,
            disconnect_mode=disconnect_mode,
            disconnect_mode_delay=disconnect_mode_delay,
            request_timeouts=request_timeouts,
            mac_address=mac_address,
            collection=collection,
            logger=logger,
        )

    @property
    def can_turn_on(self) -> bool:
        return not self.state.online and self.mac_address

    async def async_load_host_keys(self) -> None:
        """Load host keys."""
        await self._terminal.async_load_host_keys()

    async def async_turn_on(self) -> None:
        """Turn on by Wake on LAN.

        Return if already online.

        Raises:
            `ValueError`

        """
        if self.state.online:
            return

        if not self.mac_address:
            raise ValueError("No MAC Address set")

        wakeonlan.send_magic_packet(self.mac_address)
        self.log(f"Magic packet sent to {self.mac_address}")
        self.state.handle_turn_on()
