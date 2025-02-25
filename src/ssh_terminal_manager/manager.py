from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import logging

from terminal_manager import (
    DEFAULT_ALLOW_TURN_OFF,
    DEFAULT_COMMAND_TIMEOUT,
    Collection,
    CommandOutput,
    ExecutionError,
    Manager,
)
import wakeonlan

from .errors import (
    OfflineError,
    SSHAuthenticationError,
    SSHConnectError,
    SSHHostKeyUnknownError,
)
from .ping import Ping
from .ssh import SSH
from .state import Request, State

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 22
DEFAULT_PING_TIMEOUT = 4
DEFAULT_SSH_TIMEOUT = 4
DEFAULT_ADD_HOST_KEYS = False
DEFAULT_LOAD_SYSTEM_HOST_KEYS = False
DEFAULT_DISCONNECT_MODE = False
DEFAULT_INVOKE_SHELL = False


async def _run_in_executor(prefix: str, func: Callable, *args):
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(thread_name_prefix=prefix) as executor:
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
        self.state = State(self)
        self._ping = Ping(ping_timeout)
        self._ssh = SSH(
            host,
            port,
            username,
            password,
            key_filename,
            host_keys_filename,
            add_host_keys,
            load_system_host_keys,
            invoke_shell,
            ssh_timeout,
        )
        self._mac_address = None
        self.disconnect_mode = disconnect_mode

    @property
    def is_up(self) -> bool:
        if self.disconnect_mode:
            return self.state.online and self.state.request != Request.CONNECT
        return self.state.connected

    @property
    def is_down(self) -> bool:
        return not self.state.online

    @property
    def is_shutting_down(self) -> bool:
        return self.state.request in [Request.TURN_OFF, Request.RESTART]

    @property
    def host(self) -> str:
        return self._ssh.host

    @property
    def mac_address(self) -> str | None:
        return self._mac_address or super().mac_address

    def set_mac_address(self, mac_address: str | None) -> None:
        """Set the MAC address."""
        self._mac_address = mac_address

    async def async_ping(self) -> None:
        """Ping.

        Raises:
            `OfflineError`

        """
        try:
            await self._ping.async_ping(self.host)
        except OfflineError:
            self.state.handle_ping_error()
            raise
        else:
            self.state.handle_ping_success()

    async def async_connect(self) -> None:
        """Connect.

        Return if already connected. Reset sensor commands if any error occures
        and set `state.error` to `True` in case of an auth error.

        Raises:
            `SSHHostKeyUnknownError`
            `SSHAuthenticationError`
            `SSHConnectError`

        """
        if self.state.connected:
            return

        if not self.state.online:
            raise SSHConnectError("Host is offline")

        if self.is_shutting_down:
            raise SSHConnectError("Host is shutting down")

        try:
            await _run_in_executor("SSHConnect", self._ssh.connect)
        except (SSHHostKeyUnknownError, SSHAuthenticationError):
            self.state.handle_auth_error()
            raise
        except SSHConnectError:
            self.state.handle_connect_error()
            raise
        else:
            self.state.handle_connect_success()

    def disconnect(self) -> None:
        """Disconnect.

        Return if already disconnected.
        """
        if not self.state.connected:
            return

        self._ssh.disconnect()
        self.state.handle_disconnect()

    async def async_close(self) -> None:
        """Close."""
        await super().async_close()
        self.disconnect()
        self.state.online = False

    async def async_execute_command_string(
        self,
        string: str,
        command_timeout: int | None = None,
    ) -> CommandOutput:
        """Execute a command string.

        Connect before and disconnect after execution if `disconnect_mode` is
        enabled. Raise `ExecutionError` if not connected or failed to connect
        when in `disconnect_mode`. Reset sensor commands if an error occures
        while connecting or executing.

        Raises:
            `ExecutionError`

        """
        if self.disconnect_mode:
            try:
                await self.async_connect()
            except Exception as exc:
                raise ExecutionError(f"Failed to connect: {exc}") from exc

        if not self.state.connected:
            raise ExecutionError("Not connected")

        try:
            output = await _run_in_executor(
                "SSHExecute",
                self._ssh.execute_command_string,
                string,
                command_timeout or self.command_timeout,
            )
        except TimeoutError as exc:
            raise ExecutionError("Timeout during command") from exc
        except ExecutionError:
            self.state.handle_execute_error()
            raise

        if self.disconnect_mode:
            self.disconnect()

        return output

    async def async_update(
        self,
        *,
        force: bool = False,
        once: bool = False,
        test: bool = False,
        raise_errors: bool = False,
    ) -> None:
        """Update state and sensor commands, raise errors when done.

        Update all commands with `force`.
        Update only commands that have never been updated before with `once`.
        Execute a test command if there are no commands to update with `test`.
        Never execute a test command in `disconnect_mode`.

        Raises:
            `OfflineError` (only with `raise_errors`)
            `SSHHostKeyUnknownError`
            `SSHAuthenticationError`
            `SSHConnectError` (only with `raise_errors`)
            `ExecutionError` (only with `raise_errors`)

        """
        self.state.handle_update()

        if self.state.connected and not self.disconnect_mode:
            try:
                await super().async_update(
                    force=force,
                    once=once,
                    test=test,
                    raise_errors=True,
                )
            except ExecutionError:
                pass
            else:
                return

        try:
            await self.async_ping()
        except OfflineError:
            if raise_errors:
                raise
            return

        if not self.disconnect_mode:
            try:
                await self.async_connect()
            except SSHConnectError:
                if raise_errors:
                    raise
                return

        await super().async_update(
            force=force,
            test=test and not self.disconnect_mode,
            once=once,
            raise_errors=raise_errors,
        )

    async def async_turn_on(self) -> None:
        """Turn on by Wake on LAN.

        Raises:
            `ValueError`

        """
        if self.state.online:
            return

        if self.mac_address is None:
            raise ValueError("No MAC Address set")

        wakeonlan.send_magic_packet(self.mac_address)
        self.logger.debug("%s: Magic packet sent to %s", self.name, self.mac_address)
        self.state.handle_turn_on()

    async def async_turn_off(self) -> CommandOutput:
        """Turn off by running the `TURN_OFF` action.

        Raises:
            `PermissionError`
            `KeyError`
            `ExecutionError`

        """
        output = await super().async_turn_off()
        self.disconnect()
        self.state.handle_turn_off()
        return output

    async def async_restart(self) -> CommandOutput:
        """Restart by running the `RESTART` action.

        Raises:
            `KeyError`
            `ExecutionError`

        """
        output = await super().async_restart()
        self.disconnect()
        self.state.handle_restart()
        return output

    async def async_load_host_keys(self) -> None:
        """Load host keys."""
        return await _run_in_executor("SSHLoadHostKeys", self._ssh.load_host_keys)
