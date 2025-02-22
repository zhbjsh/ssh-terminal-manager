from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging

from terminal_manager import (
    DEFAULT_ALLOW_TURN_OFF,
    DEFAULT_COMMAND_TIMEOUT,
    Collection,
    Command,
    CommandError,
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
from .state import State

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
            return self.state.online
        return self.state.connected

    @property
    def is_down(self) -> bool:
        return not self.state.online

    @property
    def host(self) -> str:
        return self._ssh.host

    @property
    def mac_address(self) -> str | None:
        return self._mac_address or super().mac_address

    def set_mac_address(self, mac_address: str | None) -> None:
        """Set the MAC address."""
        self._mac_address = mac_address

    async def async_ping(self, *, raise_errors: bool = False) -> None:
        """Ping.

        Raises:
            OfflineError (only with `raise_errors=True`)

        """
        try:
            await self._ping.async_ping(self.host)
        except OfflineError:
            self.state.handle_ping_error()
            if raise_errors:
                raise
        else:
            self.state.handle_ping_success()

    async def async_connect(self, *, raise_errors: bool = False) -> None:
        """Connect.

        Return if already connected. Reset sensor commands if any error occures
        and set `state.error` to `True` in case of an auth error.

        Raises:
            SSHHostKeyUnknownError
            SSHAuthenticationError
            SSHConnectError (only with `raise_errors=True`)

        """
        if self.state.connected:
            return

        try:
            await _run_in_executor(self._ssh.connect)
        except (SSHHostKeyUnknownError, SSHAuthenticationError):
            self.state.handle_auth_error()
            raise
        except SSHConnectError:
            await self.async_disconnect()
            self.state.handle_connect_error()
            if raise_errors:
                raise
        else:
            self.state.handle_connect_success()

    async def async_disconnect(self) -> None:
        """Disconnect."""
        await _run_in_executor(self._ssh.disconnect)
        self.state.handle_disconnect()

    async def async_close(self) -> None:
        """Close."""
        await super().async_close()
        await self.async_disconnect()
        self.state.online = False

    async def async_execute_command_string(
        self,
        string: str,
        command_timeout: int | None = None,
    ) -> CommandOutput:
        """Execute a command string.

        Connect before and disconnect after execution if `disconnect_mode` is enabled.
        Raise `ExecutionError` if not online, not connected or failed to connect while
        in `disconnect_mode`.
        Reset sensor commands if an error occures while connecting or executing.

        Raises:
            ExecutionError

        """
        if not self.state.online:
            raise ExecutionError("Not online")

        if self.disconnect_mode and not self.state.connected:
            try:
                await self.async_connect(raise_errors=True)
            except Exception as exc:
                raise ExecutionError(f"Failed to connect: {exc}") from exc

        if not self.state.connected:
            raise ExecutionError("Not connected")

        try:
            output = await _run_in_executor(
                self._ssh.execute_command_string,
                string,
                command_timeout or self.command_timeout,
            )
        except TimeoutError as exc:
            raise ExecutionError("Timeout during command") from exc
        except ExecutionError:
            await self.async_disconnect()
            self.state.handle_execute_error()
            raise

        if self.disconnect_mode and self.state.connected:
            await self.async_disconnect()

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

        Commands that raised a `CommandError` count as updated.
        If `force=True`, update all commands.
        If `once=True`, update only commands that have never been updated before.
        If `test=True`, execute a test command if there are no commands to update.

        Raises:
            OfflineError (only with `raise_errors=True`)
            SSHHostKeyUnknownError
            SSHAuthenticationError
            SSHConnectError (only with `raise_errors=True`)
            CommandError (only with `raise_errors=True`)
            ExecuteError (only with `raise_errors=True`)

        """
        if self.is_up:
            try:
                await super().async_update(
                    force=force,
                    once=once,
                    test=test,
                    raise_errors=True,
                )
            except (CommandError, ExecutionError):
                pass
            else:
                return

        await self.async_ping(raise_errors=raise_errors)

        if not self.state.online:
            return

        if not self.disconnect_mode:
            await self.async_connect(raise_errors=raise_errors)

        if self.state.connected or self.disconnect_mode:
            await super().async_update(
                force=force,
                test=test,
                once=once,
                raise_errors=raise_errors,
            )

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
