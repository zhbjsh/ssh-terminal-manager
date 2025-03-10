"""SSH terminal manager."""

from terminal_manager import (
    DEFAULT_ALLOW_TURN_OFF,
    DEFAULT_COMMAND_TIMEOUT,
    PLACEHOLDER_KEY,
    ActionCommand,
    ActionKey,
    BinarySensor,
    Collection,
    Command,
    CommandError,
    CommandOutput,
    Event,
    ExecutionError,
    Manager,
    ManagerError,
    NameKeyError,
    NumberSensor,
    Sensor,
    SensorCommand,
    SensorError,
    SensorKey,
    TextSensor,
    VersionSensor,
    default_collections,
)

from .errors import (
    OfflineError,
    SSHAuthenticationError,
    SSHConnectError,
    SSHHostKeyUnknownError,
    SSHManagerError,
)
from .manager import (
    DEFAULT_ADD_HOST_KEYS,
    DEFAULT_DISCONNECT_MODE,
    DEFAULT_INVOKE_SHELL,
    DEFAULT_LOAD_SYSTEM_HOST_KEYS,
    DEFAULT_PING_TIMEOUT,
    DEFAULT_PORT,
    DEFAULT_SSH_TIMEOUT,
    SSHManager,
)
from .state import Request, State

__all__ = [
    "DEFAULT_ALLOW_TURN_OFF",
    "DEFAULT_COMMAND_TIMEOUT",
    "PLACEHOLDER_KEY",
    "ActionCommand",
    "ActionKey",
    "BinarySensor",
    "Collection",
    "Command",
    "CommandError",
    "CommandOutput",
    "Event",
    "ExecutionError",
    "Manager",
    "ManagerError",
    "NameKeyError",
    "NumberSensor",
    "Sensor",
    "SensorCommand",
    "SensorError",
    "SensorKey",
    "TextSensor",
    "VersionSensor",
    "default_collections",
    "OfflineError",
    "SSHAuthenticationError",
    "SSHConnectError",
    "SSHHostKeyUnknownError",
    "SSHManagerError",
    "DEFAULT_ADD_HOST_KEYS",
    "DEFAULT_DISCONNECT_MODE",
    "DEFAULT_INVOKE_SHELL",
    "DEFAULT_LOAD_SYSTEM_HOST_KEYS",
    "DEFAULT_PING_TIMEOUT",
    "DEFAULT_PORT",
    "DEFAULT_SSH_TIMEOUT",
    "SSHManager",
    "Request",
    "State",
]
