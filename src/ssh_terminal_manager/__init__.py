"""SSH terminal manager."""

from __future__ import annotations

import asyncio
import logging
from time import time

import paramiko
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
    Manager,
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
from .ping_client import PingClient

_LOGGER = logging.getLogger(__name__)
_TEST_COMMAND = Command("echo ''")

ONLINE = "online"
CONNECTED = "connected"
ERROR = "error"

DEFAULT_PORT = 22
DEFAULT_PING_TIMEOUT = 4
DEFAULT_SSH_TIMEOUT = 4
DEFAULT_ADD_HOST_KEYS = False
DEFAULT_LOAD_SYSTEM_HOST_KEYS = False
DEFAULT_DISCONNECT_MODE = False


logging.getLogger("paramiko").setLevel(logging.CRITICAL)


class CustomRejectPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        raise SSHHostKeyUnknownError(f"SSH host key of {hostname} is unknown")


class State:
    online: bool = False
    connected: bool = False
    error: bool = False

    def __init__(self, manager: SSHManager) -> None:
        self._manager = manager
        self.on_change = Event()

    def update(self, name, value) -> None:
        if getattr(self, name) == value:
            return

        setattr(self, name, value)
        self._manager.logger.debug(
            "%s: state.%s => %s", self._manager.name, name, value
        )
        self.on_change.notify(self)


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
        allow_turn_off: bool = DEFAULT_ALLOW_TURN_OFF,
        ssh_timeout: int = DEFAULT_SSH_TIMEOUT,
        ping_timeout: int = DEFAULT_PING_TIMEOUT,
        command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
        disconnect_mode: bool = DEFAULT_DISCONNECT_MODE,
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
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.host_keys_filename = host_keys_filename
        self.load_system_host_keys = load_system_host_keys
        self.ssh_timeout = ssh_timeout
        self.ping_timeout = ping_timeout
        self.disconnect_mode = disconnect_mode
        self._mac_address = None
        self.state = State(self)
        self.ping_client = PingClient()
        self.client = paramiko.SSHClient()
        self.client.set_log_channel("paramiko")
        self.client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy if add_host_keys else CustomRejectPolicy
        )

    @property
    def is_up(self) -> bool:
        if self.disconnect_mode:
            return self.state.online
        return self.state.connected

    @property
    def is_down(self) -> bool:
        return not self.state.online

    @property
    def mac_address(self) -> str | None:
        return self._mac_address or super().mac_address

    def _execute_command_string(self, string: str, timeout: int) -> CommandOutput:
        if self.disconnect_mode and self.state.online and not self.state.connected:
            try:
                self._connect()
            except Exception as exc:
                raise CommandError(f"Failed to connect ({exc})") from exc

        if not self.state.connected:
            raise CommandError("Not connected")

        try:
            stdin, stdout, stderr = self.client.exec_command(
                string,
                timeout=float(timeout),
            )
        except Exception as exc:
            self._disconnect()
            raise CommandError(f"Disconnected before execution ({exc})") from exc

        try:
            output = CommandOutput(
                string,
                time(),
                ["".join(line.splitlines()) for line in stdout],
                ["".join(line.splitlines()) for line in stderr],
                stdout.channel.recv_exit_status(),
            )
        except TimeoutError:
            pass
        except Exception as exc:
            self._disconnect()
            raise CommandError(f"Disconnected during execution ({exc})") from exc
        else:
            if self.disconnect_mode:
                self._disconnect(False)
            return output

        try:
            stdin.channel.close()
        except Exception as exc:
            self._disconnect()
            raise CommandError(f"Disconnected after timeout ({exc})") from exc

        raise CommandError("Channel closed after timeout")

    def _connect(self) -> None:
        if self.state.connected:
            return

        try:
            self.client.connect(
                self.host,
                self.port,
                self.username,
                self.password,
                key_filename=self.key_filename,
                timeout=self.ssh_timeout,
                allow_agent=False,
            )
        except SSHHostKeyUnknownError:
            self._disconnect()
            self.state.update(ERROR, True)
            raise
        except paramiko.AuthenticationException as exc:
            self._disconnect()
            self.state.update(ERROR, True)
            raise SSHAuthenticationError(f"SSH authentication failed ({exc})") from exc
        except Exception as exc:
            self._disconnect()
            raise SSHConnectError(f"SSH connection failed ({exc})") from exc

        self.state.update(CONNECTED, True)
        self.state.update(ERROR, False)

    def _disconnect(self, clear_sensor_commands: bool = True) -> None:
        self.client.close()
        self.state.update(CONNECTED, False)

        if not clear_sensor_commands:
            return

        for command in self.sensor_commands:
            command.update_sensors(self, None)

    def _load_host_keys(self) -> None:
        if self.load_system_host_keys:
            self.client.load_system_host_keys()
        if self.host_keys_filename:
            with open(self.host_keys_filename, "a", encoding="utf-8"):
                pass
            self.client.load_host_keys(self.host_keys_filename)

    async def async_close(self) -> None:
        await super().async_close()
        await self.async_disconnect()
        self.state.update(ONLINE, False)

    async def async_execute_command_string(
        self, string: str, command_timeout: int | None = None
    ) -> CommandOutput:
        """Execute a command string.

        Raises:
            CommandError

        """
        loop = asyncio.get_running_loop()
        timeout = command_timeout or self.command_timeout
        return await loop.run_in_executor(
            None, self._execute_command_string, string, timeout
        )

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
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect)
        await self.async_update_sensor_commands(force=True)

    async def async_disconnect(self) -> None:
        """Disconnect the SSH client.

        Set `state.connected` to `False`.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._disconnect)

    async def async_update_state(self, *, raise_errors: bool = False) -> None:
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
            online = await self.ping_client.async_ping(self.host, self.ping_timeout)
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._load_host_keys)

    def set_mac_address(self, mac_address: str | None) -> None:
        """Set the MAC address."""
        self._mac_address = mac_address
