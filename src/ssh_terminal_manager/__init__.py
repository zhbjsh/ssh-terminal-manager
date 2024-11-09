"""SSH terminal manager."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from terminal_manager import (
    DEFAULT_ALLOW_TURN_OFF,
    DEFAULT_COMMAND_TIMEOUT,
    PLACEHOLDER_KEY,
    ActionCommand,
    BinarySensor,
    Collection,
    Command,
    CommandError,
    CommandOutput,
    Event,
    InvalidRequiredSensorError,
    Manager,
    NameKeyError,
    NumberSensor,
    Sensor,
    SensorCommand,
    TextSensor,
    default_collections,
)
from terminal_manager.default_collections import ActionKey, SensorKey
import wakeonlan

from .errors import (
    OfflineError,
    SSHAuthenticationError,
    SSHConnectError,
    SSHHostKeyUnknownError,
)
from .ping import Ping
from .ssh import SSH
from .state import ONLINE, State

_LOGGER = logging.getLogger(__name__)
_TEST_COMMAND = Command("echo ''")

DEFAULT_PORT = 22
DEFAULT_PING_TIMEOUT = 4
DEFAULT_SSH_TIMEOUT = 4
DEFAULT_ADD_HOST_KEYS = False
DEFAULT_LOAD_SYSTEM_HOST_KEYS = False
DEFAULT_DISCONNECT_MODE = False
DEFAULT_INVOKE_SHELL = False


async def _run_in_executor(func, *args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(thread_name_prefix="SSH") as executor:
        return await loop.run_in_executor(executor, func, *args)


class SSHManager(Manager):
    def __init__(
        self,
        host: str,
        *,
        name: str | None = None,
        port: int = DEFAULT_PORT,
        username: str | None = None,
        password: str | None = None,
        key_filename: str | None = None,
        host_keys_filename: str | None = None,
        add_host_keys: bool = DEFAULT_ADD_HOST_KEYS,
        load_system_host_keys: bool = DEFAULT_LOAD_SYSTEM_HOST_KEYS,
        invoke_shell: bool = DEFAULT_INVOKE_SHELL,
        allow_turn_off: bool = DEFAULT_ALLOW_TURN_OFF,
        disconnect_mode: bool = DEFAULT_DISCONNECT_MODE,
        ssh_timeout: int = DEFAULT_SSH_TIMEOUT,
        ping_timeout: int = DEFAULT_PING_TIMEOUT,
        command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
        collection: Collection | None = None,
        logger: logging.Logger = _LOGGER,
    ) -> None:
        super().__init__(
            name=name or host,
            command_timeout=command_timeout,
            allow_turn_off=allow_turn_off,
            collection=collection,
            logger=logger,
        )
        self.state = State(
            self.name,
            self.logger,
        )
        self._ping = Ping(
            ping_timeout,
        )
        self._ssh = SSH(
            self.state,
            host,
            port,
            username,
            password,
            key_filename,
            host_keys_filename,
            add_host_keys,
            load_system_host_keys,
            invoke_shell,
            disconnect_mode,
            ssh_timeout,
        )
        self._ssh.on_disconnect.subscribe(self._clear_sensors)
        self._mac_address = None

    @property
    def is_up(self) -> bool:
        if self.disconnect_mode:
            return self.state.online
        return self.state.connected

    @property
    def is_down(self) -> bool:
        return not self.state.online

    @property
    def disconnect_mode(self) -> bool:
        return self._ssh.disconnect_mode

    @property
    def host(self) -> str:
        return self._ssh.host

    @property
    def mac_address(self) -> str | None:
        return self._mac_address or super().mac_address

    def set_mac_address(self, mac_address: str | None) -> None:
        """Set the MAC address."""
        self._mac_address = mac_address

    async def async_connect(self) -> None:
        """Connect the SSH client.

        Set `state.connected` to `True` and update all sensor
        commands if successful, otherwise raise an error.
        Doesnt do anything in `disconnect_mode`.

        Raises:
            SSHHostKeyUnknownError
            SSHAuthenticationError
            SSHConnectError

        """
        if self.disconnect_mode:
            return
        await _run_in_executor(self._ssh.connect)
        await self.async_update_sensor_commands(force=True)

    async def async_disconnect(self) -> None:
        """Disconnect the SSH client.

        Set `state.connected` to `False`.
        """
        await _run_in_executor(self._ssh.disconnect)

    async def async_close(self) -> None:
        """Close."""
        await super().async_close()
        await self.async_disconnect()
        self.state.update(ONLINE, False)

    async def async_execute_command_string(
        self,
        string: str,
        command_timeout: int | None = None,
    ) -> CommandOutput:
        """Execute a command string.

        Raises:
            CommandError

        """
        timeout = command_timeout or self.command_timeout
        return await _run_in_executor(self._ssh.execute_command_string, string, timeout)

    async def async_update_state(
        self,
        *,
        raise_errors: bool = False,
    ) -> None:
        """Update state.

        Raises:
            OfflineError (only with `raise_errors=True`)
            SSHHostKeyUnknownError
            SSHAuthenticationError
            SSHConnectError (only with `raise_errors=True`)

        """
        if self.state.connected:
            try:
                await self.async_execute_command(_TEST_COMMAND)
            except CommandError:
                pass
            else:
                return

        try:
            online = await self._ping.async_ping(self.host)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("%s: Ping request failed (%s)", self.name, exc)
            self.state.update(ONLINE, False)
        else:
            self.state.update(ONLINE, online)

        if not self.state.online:
            if raise_errors:
                raise OfflineError("Host is offline")
            return

        try:
            await self.async_connect()
        except SSHConnectError:
            if raise_errors:
                raise

    async def async_turn_on(self) -> None:
        """Turn on by Wake on LAN.

        Raises:
            ValueError

        """
        if self.mac_address is None:
            raise ValueError("No MAC Address set")

        wakeonlan.send_magic_packet(self.mac_address)
        self.logger.debug("%s: Magic packet sent to %s", self.name, self.mac_address)

    async def async_load_host_keys(self) -> None:
        """Load host keys."""
        return await _run_in_executor(self._ssh.load_host_keys)
