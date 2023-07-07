"""SSH terminal manager."""
from __future__ import annotations

import asyncio
import logging
from time import time

import icmplib
import paramiko
from terminal_manager import (
    DEFAULT_COMMAND_TIMEOUT,
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

from .errors import OfflineError, SSHAuthError, SSHConnectError, SSHHostKeyUnknownError

_LOGGER = logging.getLogger(__name__)
_TEST_COMMAND = Command("echo ''")

DEFAULT_PORT = 22
DEFAULT_PING_TIMEOUT = 4
DEFAULT_SSH_TIMEOUT = 4
DEFAULT_ADD_HOST_KEYS = False
DEFAULT_ALLOW_TURN_OFF = False

ONLINE = "online"
CONNECTED = "connected"


class CustomRejectPolicy(paramiko.MissingHostKeyPolicy):
    """Custom reject policy for ssh client."""

    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        raise SSHHostKeyUnknownError("Host key is unknown")


class State:
    """The State class."""

    online: bool = False
    connected: bool = False

    def __init__(self, manager: SSHManager) -> None:
        self._manager = manager
        self.on_change = Event()

    def update(self, name, value) -> None:
        """Update."""
        if getattr(self, name) == value:
            return

        setattr(self, name, value)
        self._manager.logger.debug("%s: %s is %s", self._manager.name, name, value)
        self.on_change.notify(self)


class SSHManager(Manager):
    """The SSHManager class."""

    def __init__(
        self,
        host: str,
        *,
        name: str | None = None,
        mac_address: str | None = None,
        add_host_keys: bool = DEFAULT_ADD_HOST_KEYS,
        port: int = DEFAULT_PORT,
        username: str | None = None,
        password: str | None = None,
        key_filename: str | None = None,
        host_keys_filename: str | None = None,
        ssh_timeout: int = DEFAULT_SSH_TIMEOUT,
        ping_timeout: int = DEFAULT_PING_TIMEOUT,
        command_timeout: int = DEFAULT_COMMAND_TIMEOUT,
        collection: Collection | None = None,
        allow_turn_off: bool = DEFAULT_ALLOW_TURN_OFF,
        logger: logging.Logger = _LOGGER,
    ) -> None:
        super().__init__(
            name=name or host,
            command_timeout=command_timeout,
            collection=collection,
            logger=logger,
        )
        self.host = host
        self._mac_address = mac_address
        self.port = port
        self.username = username
        self.password = password
        self.key_filename = key_filename
        self.ssh_timeout = ssh_timeout
        self.ping_timeout = ping_timeout
        self.allow_turn_off = allow_turn_off
        self.state = State(self)
        self._client = paramiko.SSHClient()
        self._client.load_system_host_keys()
        self._client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy if add_host_keys else CustomRejectPolicy
        )

        if host_keys_filename:
            with open(host_keys_filename, "a", encoding="utf-8"):
                pass
            self._client.load_host_keys(host_keys_filename)

    @property
    def hostname(self) -> str | None:
        """Hostname."""
        if sensor := self.sensors_by_key.get(SensorKey.HOSTNAME):
            return sensor.last_known_value

    @property
    def mac_address(self) -> str | None:
        """MAC address."""
        if self._mac_address:
            return self._mac_address
        if sensor := self.sensors_by_key.get(SensorKey.MAC_ADDRESS):
            return sensor.last_known_value

    @property
    def wol_support(self) -> bool | None:
        """Wake on LAN support."""
        if sensor := self.sensors_by_key.get(SensorKey.WOL_SUPPORT):
            return sensor.last_known_value

    @property
    def os_name(self) -> str | None:
        """OS name."""
        if sensor := self.sensors_by_key.get(SensorKey.OS_NAME):
            return sensor.last_known_value

    @property
    def os_version(self) -> str | None:
        """OS version."""
        if sensor := self.sensors_by_key.get(SensorKey.OS_VERSION):
            return sensor.last_known_value

    @property
    def machine_type(self) -> str | None:
        """Machine type."""
        if sensor := self.sensors_by_key.get(SensorKey.MACHINE_TYPE):
            return sensor.last_known_value

    def _execute_command_string(self, string: str, timeout: int) -> CommandOutput:
        if not self.state.connected:
            raise CommandError("Not connected")

        try:
            stdin, stdout, stderr = self._client.exec_command(
                string,
                timeout=float(timeout),
            )
        except Exception as exc:
            self._disconnect()
            raise CommandError("Disconnected before execution") from exc

        try:
            return CommandOutput(
                time(),
                ["".join(line.splitlines()) for line in stdout],
                ["".join(line.splitlines()) for line in stderr],
                stdout.channel.recv_exit_status(),
            )
        except TimeoutError as exc:
            stdin.channel.close()
            raise CommandError(f"Timeout ({timeout} s)") from exc
        except Exception as exc:
            self._disconnect()
            raise CommandError("Disconnected during execution") from exc

    def _connect(self) -> None:
        if self.state.connected:
            return

        try:
            self._client.connect(
                self.host,
                self.port,
                self.username,
                self.password,
                key_filename=self.key_filename,
                timeout=self.ssh_timeout,  # timeout for the TCP connect
                allow_agent=False,
            )
        except SSHHostKeyUnknownError:
            self._disconnect()
            raise
        except paramiko.AuthenticationException as exc:
            self._disconnect()
            raise SSHAuthError("SSH authentication failed") from exc
        except Exception as exc:
            self._disconnect()
            raise SSHConnectError("SSH connection failed") from exc

        self.state.update(CONNECTED, True)

    def _disconnect(self) -> None:
        if not self.state.connected:
            return

        self._client.close()
        self.state.update(CONNECTED, False)

        for command in self.sensor_commands:
            command.update_sensors(self, None)

    async def async_execute_command_string(
        self, string: str, command_timeout: int | None = None
    ) -> CommandOutput:
        loop = asyncio.get_running_loop()
        timeout = command_timeout or self.command_timeout
        return await loop.run_in_executor(
            None, self._execute_command_string, string, timeout
        )

    async def async_connect(self) -> None:
        """Connect the SSH client.

        Set `state.connected` to `True` and update all
        sensor commands if successful, otherwise disconnect
        and raise an error.

        Raises:
            SSHHostKeyUnknownError
            SSHAuthError
            SSHConnectError
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect)

        for command in self.sensor_commands:
            try:
                await self.async_execute_command(command)
            except CommandError:
                pass

    async def async_disconnect(self) -> None:
        """Disconnect the SSH client.

        Set `state.connected` to `False` and
        update all sensor commands with `None`.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._disconnect)

    async def async_update_state(self, *, raise_errors: bool = False) -> None:
        """Update state.

        Raises:
            OfflineError (`raise_errors`)
            SSHHostKeyUnknownError
            SSHAuthError
            SSHConnectError (`raise_errors`)
        """
        if self.state.connected:
            try:
                await self.async_execute_command(_TEST_COMMAND)
                return
            except CommandError:
                pass

        try:
            host = await icmplib.async_ping(
                self.host,
                count=1,
                timeout=self.ping_timeout,
                privileged=False,
            )
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.debug("%s: Ping request failed (%s)", self.name, exc)
            self.state.update(ONLINE, False)
        else:
            self.state.update(ONLINE, host.is_alive)

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
        """Turn the host on."""
        if self.state.online:
            return

        wakeonlan.send_magic_packet(self.mac_address)

    async def async_turn_off(self) -> None:
        """Turn the host off.

        Raises:
            CommandError
        """
        if self.allow_turn_off is False:
            return

        await self.async_run_action(ActionKey.TURN_OFF)
