import logging
import re
import time

import paramiko
from terminal_manager import CommandError, CommandOutput, Event

from .errors import SSHAuthenticationError, SSHConnectError, SSHHostKeyUnknownError
from .state import CONNECTED, ERROR, State

WIN_TITLE = re.compile(r"\x1B\]0\;.*?\x07")
WIN_NEWLINE = re.compile(r"\x1B\[\d+\;1H")
ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

END = "__exit_code__"
PS_CODE = "$LastExitCode"
LINUX_CODE = "$?"
CMD_CODE = r"%errorlevel%"
BASH_PIPE = r"${PIPESTATUS[@]}"
ZSH_PIPE = r"${pipestatus[@]}"

ECHO_STRING = f'echo "{END}|{PS_CODE}|{LINUX_CODE}|{CMD_CODE}|{BASH_PIPE}|{ZSH_PIPE}"'
EXIT_STRING = "exit"

logging.getLogger("paramiko").setLevel(logging.CRITICAL)


def _format(string: str) -> str:
    string = WIN_TITLE.sub("", string)
    string = WIN_NEWLINE.sub("\n", string)
    string = ANSI_ESCAPE.sub("", string)
    return string.replace("\b", "").replace("\r", "")


def _get_exit_code(line: str) -> int:
    fields = line.split("|")

    if len(fields) != 6:
        return 0

    pipe_bash, pipe_zsh = fields[4:]

    for item in pipe_bash.split() + pipe_zsh.split():
        if item.isnumeric() and item != "0":
            return int(item)

    for item in fields[:4]:
        if item.isnumeric():
            return int(item)
        if item == "True":
            return 0
        if item == "False":
            return 1

    return 0


def _get_index(lines: list[str], string: str) -> int | None:
    for i, line in enumerate(lines):
        if string in line:
            return i
    return None


class CustomRejectPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        raise SSHHostKeyUnknownError(f"SSH host key of {hostname} is unknown")


class SSH:
    def __init__(
        self,
        state: State,
        host: str,
        port: int,
        username: str,
        password: str,
        key_filename: str,
        host_keys_filename: str,
        add_host_keys: bool,
        load_system_host_keys: bool,
        invoke_shell: bool,
        disconnect_mode: bool,
        timeout: int,
    ):
        self._state = state
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._key_filename = key_filename
        self._host_keys_filename = host_keys_filename
        self._load_system_host_keys = load_system_host_keys
        self._timeout = timeout
        self._disconnect_mode = disconnect_mode
        self._invoke_shell = invoke_shell
        self._client = paramiko.SSHClient()
        self._client.set_log_channel("paramiko")
        self._client.set_missing_host_key_policy(
            paramiko.AutoAddPolicy if add_host_keys else CustomRejectPolicy
        )
        self.on_disconnect = Event()

    @property
    def host(self) -> str:
        return self._host

    @property
    def disconnect_mode(self) -> bool:
        return self._disconnect_mode

    def connect(self) -> None:
        if self._state.connected:
            return

        try:
            self._client.connect(
                self._host,
                self._port,
                self._username,
                self._password,
                key_filename=self._key_filename,
                timeout=self._timeout,
                allow_agent=False,
            )
        except SSHHostKeyUnknownError:
            self.disconnect()
            self._state.update(ERROR, True)
            raise
        except paramiko.AuthenticationException as exc:
            self.disconnect()
            self._state.update(ERROR, True)
            raise SSHAuthenticationError(f"SSH authentication failed ({exc})") from exc
        except Exception as exc:
            self.disconnect()
            raise SSHConnectError(f"SSH connection failed ({exc})") from exc

        self._state.update(CONNECTED, True)
        self._state.update(ERROR, False)

    def disconnect(self, notify: bool = True) -> None:
        self._client.close()
        self._state.update(CONNECTED, False)

        if notify:
            self.on_disconnect.notify()

    def load_host_keys(self) -> None:
        if self._load_system_host_keys:
            self._client.load_system_host_keys()
        if self._host_keys_filename:
            with open(self._host_keys_filename, "a", encoding="utf-8"):
                pass
            self._client.load_host_keys(self._host_keys_filename)

    def execute_command_string(self, string: str, timeout: int) -> CommandOutput:
        if self._disconnect_mode and self._state.online and not self._state.connected:
            try:
                self.connect()
            except Exception as exc:
                raise CommandError(f"Failed to connect ({exc})") from exc

        if not self._state.connected:
            raise CommandError("Not connected")

        try:
            if self._invoke_shell:
                return self._execute_invoke_shell(string, timeout)
            return self._execute(string, timeout)
        except TimeoutError as exc:
            raise CommandError(f"Timeout during command ({exc})") from exc
        except CommandError:
            self.disconnect()
            raise
        finally:
            if self._disconnect_mode and self._state.connected:
                self.disconnect(False)

    def _execute(self, string: str, timeout: int) -> CommandOutput:
        try:
            stdin, stdout, stderr = self._client.exec_command(
                string,
                timeout=float(timeout),
            )
        except Exception as exc:
            raise CommandError(f"Failed to execute command ({exc})") from exc

        try:
            return CommandOutput(
                string,
                time.time(),
                ["".join(line.splitlines()) for line in stdout],
                ["".join(line.splitlines()) for line in stderr],
                stdout.channel.recv_exit_status(),
            )
        except TimeoutError:
            stdin.channel.close()
            raise
        except Exception as exc:
            raise CommandError(f"Failed to read command output ({exc})") from exc

    def _execute_invoke_shell(self, string: str, timeout: int) -> CommandOutput:
        try:
            channel = self._client.invoke_shell(width=800)
        except Exception as exc:
            raise CommandError(f"Failed to open channel ({exc})") from exc

        channel.settimeout(float(timeout))
        stdin_file = channel.makefile_stdin("wb")
        stdout_file = channel.makefile("r")
        stderr_file = channel.makefile_stderr("r")

        # needed for windows cmd:
        while not channel.recv_ready():
            time.sleep(0.2)

        try:
            stdin_file.write(string + "\r")
            # needed for windows cmd:
            time.sleep(1)
            stdin_file.write(ECHO_STRING + "\r")
            stdin_file.write(EXIT_STRING + "\r")
        except Exception as exc:
            raise CommandError(f"Failed to send command ({exc})") from exc

        try:
            stdout_string = _format(stdout_file.read().decode())
            stderr_string = _format(stderr_file.read().decode())
        except TimeoutError:
            raise
        except Exception as exc:
            raise CommandError(f"Failed to read command output ({exc})") from exc
        finally:
            channel.close()

        stdout = []
        stderr = stderr_string.splitlines()
        code = 0

        for line in stdout_string.splitlines():
            if line in [string, ECHO_STRING, EXIT_STRING]:
                stdout = []
            elif line.startswith((END, f'"{END}')):
                code = _get_exit_code(line)
                break
            else:
                stdout.append(line)

        if stdout and string in stdout[0]:
            stdout.pop(0)
        elif (i := _get_index(stdout, string)) is not None:
            stdout = stdout[i + 1 :]

        if stdout and ECHO_STRING in stdout[-1]:
            stdout.pop()
        elif (i := _get_index(stdout, ECHO_STRING)) is not None:
            stdout = stdout[: i - 1]

        return CommandOutput(
            string,
            time.time(),
            stdout,
            stderr,
            code,
        )
