import logging
import re
import time

import paramiko
from terminal_manager import CommandOutput, Event, ExecutionError

from .errors import SSHAuthenticationError, SSHConnectError, SSHHostKeyUnknownError
from .state import State

WIN_TITLE = re.compile(r"\x1b\]0\;.*?\x07")
WIN_NEWLINE = re.compile(r"\x1b\[\d+\;1H")
ANSI_ESCAPE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

END = "__exit_code__"
PS_CODE = "$LastExitCode"
LINUX_CODE = "$?"
CMD_CODE = r"%errorlevel%"
BASH_PIPE = r"${PIPESTATUS[@]}"
ZSH_PIPE = r"${pipestatus[@]}"

ECHO_STRING = f'echo "{END}|{PS_CODE}|{LINUX_CODE}|{CMD_CODE}|{BASH_PIPE}|{ZSH_PIPE}"'
EXIT_STRING = "exit"

CMD_START = "\x1b[?25l\x1b[2J\x1b[m\x1b[H"
CMD_TEST = "Microsoft Windows"

logging.getLogger("paramiko").setLevel(logging.CRITICAL)


class CustomRejectPolicy(paramiko.MissingHostKeyPolicy):
    def missing_host_key(
        self, client: paramiko.SSHClient, hostname: str, key: paramiko.PKey
    ) -> None:
        raise SSHHostKeyUnknownError(hostname)


class ShellParser:
    def __init__(self, stdin: list[str]) -> None:
        self._stdin = stdin

    def _get_code(self, line: str) -> tuple[int, int]:
        if len(fields := line.split("|")) != 6:
            return 0

        for item in fields[:4]:
            if item.isnumeric() and (code := int(item)) != 0:
                return code
            if item == "False":
                return 1

        if len(self._stdin) > 1:
            return 0

        for item in fields[4].split() + fields[5].split():
            if item.isnumeric() and (code := int(item)) != 0:
                return int(item)

        return 0

    def _get_lines(self, stdout_bytes: bytes) -> list[str]:
        string = stdout_bytes.decode()
        string = WIN_TITLE.sub("", string)
        string = WIN_NEWLINE.sub("\n", string)
        string = ANSI_ESCAPE.sub("", string)
        string = string.replace("\b", "").replace("\r", "").replace("\0", "")
        return string.splitlines()

    def parse(self, stdout_bytes: bytes) -> tuple[list[str], int]:
        """Get stdout and code."""
        stdout = []
        code = stdin_count = start = end = 0

        for i, line in enumerate(lines := self._get_lines(stdout_bytes)):
            if stdin_count > len(self._stdin) - 1:
                break
            if line.endswith(self._stdin[stdin_count]) or line in [
                *self._stdin,
                ECHO_STRING,
                EXIT_STRING,
            ]:
                start = end = i + 1
            elif line.endswith(ECHO_STRING):
                end = i
            elif line.startswith((END, f'"{END}')):
                stdout.extend(lines[start:end])
                code = code or self._get_code(line)
                start = end = i + 1
                stdin_count += 1

        return stdout, code


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
            self._state.error = True
            raise
        except paramiko.AuthenticationException as exc:
            self.disconnect()
            self._state.error = True
            if exc.__class__ == paramiko.AuthenticationException:
                raise SSHAuthenticationError from exc
            raise SSHAuthenticationError(str(exc)) from exc
        except OSError as exc:
            self.disconnect()
            raise SSHConnectError(exc.strerror) from exc
        except Exception as exc:
            self.disconnect()
            raise SSHConnectError(str(exc)) from exc

        self._state.connected = True
        self._state.error = False

    def disconnect(self, notify: bool = True) -> None:
        self._client.close()
        self._state.connected = False

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
                raise ExecutionError(f"Failed to connect: {exc}") from exc

        if not self._state.connected:
            raise ExecutionError("Not connected")

        try:
            if self._invoke_shell:
                return self._execute_invoke_shell(string, timeout)
            return self._execute(string, timeout)
        except TimeoutError as exc:
            raise ExecutionError("Timeout during command") from exc
        except ExecutionError:
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
            raise ExecutionError(f"Failed to execute command: {exc}") from exc

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
            raise ExecutionError(f"Failed to read command output: {exc}") from exc

    def _execute_invoke_shell(self, string: str, timeout: int) -> CommandOutput:
        try:
            channel = self._client.invoke_shell(width=4095)
        except Exception as exc:
            raise ExecutionError(f"Failed to open channel: {exc}") from exc

        channel.settimeout(float(timeout))
        stdin_file = channel.makefile_stdin("wb")
        stdout_file = channel.makefile("r")

        try:
            cmd = self._detect_cmd(stdout_file)
        except Exception as exc:
            raise ExecutionError(f"Failed to detect shell: {exc}") from exc

        try:
            for line in (stdin := string.splitlines()):
                stdin_file.write(line + "\r")
                if cmd:
                    time.sleep(1.5)
                stdin_file.write(ECHO_STRING + "\r")
            stdin_file.write(EXIT_STRING + "\r")
        except Exception as exc:
            raise ExecutionError(f"Failed to send command: {exc}") from exc

        try:
            stdout_bytes = stdout_file.read()
        except TimeoutError:
            raise
        except Exception as exc:
            raise ExecutionError(f"Failed to read command output: {exc}") from exc
        finally:
            channel.close()

        try:
            stdout, code = ShellParser(stdin).parse(stdout_bytes)
        except Exception as exc:
            raise ExecutionError(f"Failed to parse command output: {exc}") from exc

        return CommandOutput(
            string,
            time.time(),
            stdout,
            [],
            code,
        )

    def _detect_cmd(self, stdout_file: paramiko.ChannelFile) -> bool:
        if stdout_file.read(16).decode() != CMD_START:
            return False

        test_line = ""
        char = stdout_file.read(1).decode()

        while char in ["\r", "\n"]:
            char = stdout_file.read(1).decode()

        while char not in ["\r", "\n"]:
            test_line += char
            char = stdout_file.read(1).decode()

        return CMD_TEST in test_line
