class OfflineError(Exception):
    """Error to indicate host is offline."""


class SSHHostKeyUnknownError(Exception):
    """Error to indicate SSH host key is unknown."""


class SSHAuthError(Exception):
    """Error to indicate SSH authentication failed."""


class SSHConnectError(Exception):
    """Error to indicate SSH connection failed."""
