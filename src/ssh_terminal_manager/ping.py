import asyncio
from contextlib import suppress

import icmplib


class Ping:
    use_icmplib: bool | None = None

    def __init__(self, timeout: int) -> None:
        self._timeout = timeout

    async def _async_test_icmplib(self) -> bool:
        try:
            await icmplib.async_ping("127.0.0.1", count=0, timeout=0, privileged=False)
        except icmplib.SocketPermissionError:
            return False
        return True

    async def _async_ping_icmplib(self, host: str) -> bool:
        result = await icmplib.async_ping(
            host,
            count=1,
            timeout=self._timeout,
            privileged=False,
        )
        return result.is_alive

    async def _async_ping_process(self, host: str) -> bool:
        process = await asyncio.create_subprocess_exec(
            "ping",
            "-q",
            "-c1",
            f"-W{self._timeout}",
            host,
            stdin=None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            close_fds=False,
        )
        try:
            async with asyncio.timeout(self._timeout + 1):
                await process.communicate()
        except TimeoutError:
            if process:
                with suppress(TypeError):
                    await process.kill()
            return False

        if process.returncode and process.returncode > 1:
            raise RuntimeError(f"Exit code: {process.returncode}")

        return process.returncode == 0

    async def async_ping(self, host: str):
        if self.use_icmplib is None:
            self.use_icmplib = await self._async_test_icmplib()

        if self.use_icmplib:
            return await self._async_ping_icmplib(host)

        return await self._async_ping_process(host)
