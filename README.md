# SSH Terminal Manager

## Initialize

```python
from ssh_terminal_manager import SSHManager

manager = SSHManager("192.168.0.123", username="user", password="1234")

await manager.async_update_state(raise_errors=True)
```
