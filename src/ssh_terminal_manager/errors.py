class OfflineError(Exception):
    """Error to indicate that the host is offline."""


class SSHHostKeyUnknownError(Exception):
    """Error to indicate that the SSH host key is unknown."""


class SSHAuthenticationError(Exception):
    """Error to indicate that the SSH authentication failed."""


class SSHConnectError(Exception):
    """Error to indicate that the SSH connection failed."""
