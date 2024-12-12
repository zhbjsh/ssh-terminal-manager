import paramiko
from terminal_manager import ManagerError


class SSHManagerError(ManagerError):
    """Base class for SSH terminal manager errors."""


class OfflineError(SSHManagerError):
    """Error to indicate that the host is offline."""

    def __init__(self, host: str) -> None:
        super().__init__(f"Host {host} is offline")
        self.host = host


class SSHHostKeyUnknownError(SSHManagerError):
    """Error to indicate that the SSH host key is unknown."""

    def __init__(self, host: str) -> None:
        super().__init__(f"SSH host key of {host} is unknown")
        self.host = host


class SSHAuthenticationError(SSHManagerError):
    """Error to indicate that the SSH authentication failed."""

    def __init__(self, exc: Exception) -> None:
        super().__init__("SSH authentication failed", exc)
        if exc.__class__ == paramiko.AuthenticationException:
            self.details = None


class SSHConnectError(SSHManagerError):
    """Error to indicate that the SSH connection failed."""

    def __init__(self, exc: Exception) -> None:
        super().__init__("SSH connection failed", exc)
        if isinstance(exc, OSError):
            self.details = exc.strerror
