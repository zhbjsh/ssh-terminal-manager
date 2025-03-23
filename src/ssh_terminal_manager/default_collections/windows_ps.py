"""The Windows PowerShell collection."""

from __future__ import annotations

from terminal_manager import (
    ActionCommand,
    ActionKey,
    BinarySensor,
    Collection,
    NumberSensor,
    SensorCommand,
    SensorKey,
    TextSensor,
)

windows_ps = Collection(
    "Windows (Power Shell)",
    [
        ActionCommand(
            "Stop-Computer -Force",
            key=ActionKey.TURN_OFF,
        ),
        ActionCommand(
            "Restart-Computer -Force",
            key=ActionKey.RESTART,
        ),
    ],
    [
        SensorCommand(
            "$x = Get-NetAdapterPowerManagement "
            '-Name "&{network_interface}" | '
            "Select WakeOnMagicPacket; "
            "$x.WakeOnMagicPacket",
            sensors=[
                BinarySensor(key=SensorKey.WAKE_ON_LAN),
            ],
        ),
        SensorCommand(
            "$y = Get-CimInstance Win32_IP4RouteTable "
            "-Filter \"Destination='0.0.0.0'\" | "
            "Select InterfaceIndex; "
            "$x = Get-CimInstance Win32_NetworkAdapter "
            "-Property NetConnectionID, InterfaceIndex, MACAddress "
            '-Filter "InterfaceIndex=$($y.InterfaceIndex)" | '
            "Select MACAddress,NetConnectionID; "
            "$x.MACAddress; "
            "$x.NetConnectionID",
            sensors=[
                TextSensor(key=SensorKey.MAC_ADDRESS),
                TextSensor(key=SensorKey.NETWORK_INTERFACE),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_ComputerSystem | "
            "Select Name,SystemType; "
            "$x.Name; "
            "$x.SystemType",
            sensors=[
                TextSensor(key=SensorKey.HOSTNAME),
                TextSensor(key=SensorKey.MACHINE_TYPE),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_OperatingSystem | "
            "Select Caption,Version,OSArchitecture; "
            "$x.Caption; "
            "$x.Version; "
            "$x.OSArchitecture",
            sensors=[
                TextSensor(key=SensorKey.OS_NAME),
                TextSensor(key=SensorKey.OS_VERSION),
                TextSensor(key=SensorKey.OS_ARCHITECTURE),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_ComputerSystemProduct | "
            "Select Vendor,Name,Version; "
            "$x.Name; "
            "$x.Version; "
            "$x.Vendor",
            sensors=[
                TextSensor(key=SensorKey.DEVICE_NAME),
                TextSensor(key=SensorKey.DEVICE_MODEL),
                TextSensor(key=SensorKey.MANUFACTURER),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_BIOS | "
            "Select SerialNumber; "
            "$x.SerialNumber",
            sensors=[
                TextSensor(key=SensorKey.SERIAL_NUMBER),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_Processor | "
            "Select Name,NumberOfCores; "
            "$x.Name; "
            "$x.NumberOfCores",
            sensors=[
                TextSensor(key=SensorKey.CPU_NAME),
                NumberSensor(key=SensorKey.CPU_CORES),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_ComputerSystem | "
            "Select TotalPhysicalMemory; "
            "$x.TotalPhysicalMemory",
            sensors=[
                NumberSensor(key=SensorKey.TOTAL_MEMORY, unit="B"),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_OperatingSystem | "
            "Select FreePhysicalMemory; "
            "$x.FreePhysicalMemory",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.FREE_MEMORY, unit="kB"),
            ],
        ),
        SensorCommand(
            "Get-CimInstance Win32_LogicalDisk | "
            "Select DeviceID,FreeSpace | "
            'ForEach-Object {$_.DeviceID + "|" + $_.FreeSpace}',
            interval=60,
            separator="|",
            sensors=[
                NumberSensor(key=SensorKey.FREE_DISK_SPACE, dynamic=True, unit="B")
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance Win32_Processor | "
            "Select LoadPercentage; "
            "$x.LoadPercentage",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.CPU_LOAD, unit="%"),
            ],
        ),
        SensorCommand(
            "$x = Get-CimInstance msacpi_thermalzonetemperature "
            '-namespace "root/wmi" | '
            "Select CurrentTemperature; "
            "($x.CurrentTemperature - 2732) / 10",
            interval=60,
            sensors=[
                NumberSensor(key=SensorKey.TEMPERATURE, unit="°C"),
            ],
        ),
        SensorCommand(
            "Get-Process | Measure | ForEach-Object {$_.Count}",
            interval=60,
            sensors=[
                NumberSensor(SensorKey.PROCESSES),
            ],
        ),
    ],
)
