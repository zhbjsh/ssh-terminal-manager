"""The Windows cmd collection."""

from __future__ import annotations

from terminal_manager import (
    ActionCommand,
    ActionKey,
    Collection,
    NumberSensor,
    SensorCommand,
    SensorKey,
    TextSensor,
)

windows_cmd = Collection(
    "Windows",
    [
        ActionCommand(
            "shutdown /s /t 0",
            key=ActionKey.TURN_OFF,
        ),
        ActionCommand(
            "shutdown /r /t 0",
            key=ActionKey.RESTART,
        ),
    ],
    [
        # TODO: WAKE_ON_LAN
        SensorCommand(
            "for /f %i in ('wmic path win32_ip4routetable "
            "where \"Destination='0.0.0.0'\" "
            "get InterfaceIndex ^| "
            'findstr /r "\\<[0-9][0-9]*\\>"\') do '
            '@for /f "skip=2 tokens=2,3 delims=," %j in (\'wmic nic '
            'where "InterfaceIndex=%i" '
            "get MACAddress^,NetConnectionID /format:csv') do "
            "@echo %j & @echo %k",
            sensors=[
                TextSensor(key=SensorKey.MAC_ADDRESS),
                TextSensor(key=SensorKey.NETWORK_INTERFACE),
            ],
        ),
        SensorCommand(
            "hostname",
            sensors=[
                TextSensor(key=SensorKey.HOSTNAME),
            ],
        ),
        SensorCommand(
            'for /f "skip=1 tokens=*" %i in (\'wmic ComputerSystem '
            "get SystemType') do "
            "@echo %i",
            sensors=[
                TextSensor(key=SensorKey.MACHINE_TYPE),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic OS get Caption') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.OS_NAME),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1\" %i in ('wmic OS get Version') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.OS_VERSION),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1\" %i in ('wmic OS get OSArchitecture') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.OS_ARCHITECTURE),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic csproduct get Name') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.DEVICE_NAME),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic csproduct get Version') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.DEVICE_MODEL),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic csproduct get Vendor') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.MANUFACTURER),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic bios get SerialNumber') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.SERIAL_NUMBER),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1 tokens=*\" %i in ('wmic cpu get Name') do @echo %i",
            sensors=[
                TextSensor(key=SensorKey.CPU_NAME),
            ],
        ),
        SensorCommand(
            "for /f \"skip=1\" %i in ('wmic cpu get NumberOfCores') do @echo %i",
            sensors=[
                NumberSensor(key=SensorKey.CPU_CORES),
            ],
        ),
        SensorCommand(
            'for /f "skip=1" %i in (\'wmic ComputerSystem '
            "get TotalPhysicalMemory') do "
            "@echo %i",
            sensors=[
                NumberSensor(key=SensorKey.TOTAL_MEMORY, unit="B"),
            ],
        ),
        SensorCommand(
            'for /f "skip=1" %i in (\'wmic OS '
            "get FreePhysicalMemory') do "
            "@echo %i",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.FREE_MEMORY, unit="kB"),
            ],
        ),
        SensorCommand(
            'for /f "tokens=1,2" %i in (\'wmic LogicalDisk '
            "get DeviceID^,FreeSpace ^| "
            'findstr ":"\') do '
            "@echo %i^|%j",
            interval=60,
            separator="|",
            sensors=[
                NumberSensor(key=SensorKey.FREE_DISK_SPACE, dynamic=True, unit="B")
            ],
        ),
        SensorCommand(
            "for /f \"skip=1\" %i in ('wmic CPU get LoadPercentage') do @echo %i",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.CPU_LOAD, unit="%"),
            ],
        ),
        SensorCommand(
            "for /f %i in ('wmic /namespace:\\\\root\\wmi "
            "path MSAcpi_ThermalZoneTemperature "
            "get CurrentTemperature ^| "
            'findstr /r "\\<[0-9][0-9]*\\>"\') do '
            "@set /a x=(%i - 2732) / 10",
            interval=60,
            sensors=[
                NumberSensor(key=SensorKey.TEMPERATURE, unit="°C"),
            ],
        ),
        SensorCommand(
            "wmic process get processId | "
            'findstr /r "\\<[0-9][0-9]*\\>" | '
            'find /c /v ""',
            interval=60,
            sensors=[
                NumberSensor(key=SensorKey.PROCESSES),
            ],
        ),
    ],
)
