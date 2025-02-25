from __future__ import annotations

from terminal_manager import ManagerError


class SSHManagerError(ManagerError):
    """Base class for SSH terminal manager errors."""


class OfflineError(SSHManagerError):
    """Error to indicate that the host is offline."""

    def __init__(self, host: str, details: str | None = None) -> None:
        super().__init__(f"Host {host} is offline", details)
        self.host = host


class SSHHostKeyUnknownError(SSHManagerError):
    """Error to indicate that the SSH host key is unknown."""

    def __init__(self, host: str) -> None:
        super().__init__(f"SSH host key of {host} is unknown")
        self.host = host


class SSHAuthenticationError(SSHManagerError):
    """Error to indicate that the SSH authentication failed."""

    def __init__(self, details: str | None = None) -> None:
        super().__init__("SSH authentication failed", details)


class SSHConnectError(SSHManagerError):
    """Error to indicate that the SSH connection failed."""

    def __init__(self, details: str) -> None:
        super().__init__("SSH connection failed", details)
