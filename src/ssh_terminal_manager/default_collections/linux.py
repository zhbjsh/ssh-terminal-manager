"""The Linux collection."""

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

linux = Collection(
    "Linux",
    [
        ActionCommand(
            "/sbin/shutdown -h now",
            key=ActionKey.TURN_OFF,
        ),
        ActionCommand(
            "/sbin/shutdown -r now",
            key=ActionKey.RESTART,
        ),
    ],
    [
        # TODO: OS_ARCHITECTURE
        SensorCommand(
            "x=$(/sbin/ip route show default 2>/dev/null) && awk '{print $5}' <<<$x || "
            "x=$(/sbin/route -n 2>/dev/null) && awk '/^0.0.0.0/ {print $NF}' <<<$x",
            sensors=[
                TextSensor(key=SensorKey.NETWORK_INTERFACE),
            ],
        ),
        SensorCommand(
            "cat /sys/class/net/&{network_interface}/address",
            sensors=[
                TextSensor(key=SensorKey.MAC_ADDRESS),
            ],
        ),
        SensorCommand(
            "cat /sys/class/net/&{network_interface}/device/power/wakeup",
            sensors=[
                BinarySensor(key=SensorKey.WAKE_ON_LAN),
            ],
        ),
        SensorCommand(
            "uname -n",
            sensors=[
                TextSensor(key=SensorKey.HOSTNAME),
            ],
        ),
        SensorCommand(
            "uname -m",
            sensors=[
                TextSensor(key=SensorKey.MACHINE_TYPE),
            ],
        ),
        SensorCommand(
            "uname -s",
            sensors=[
                TextSensor(key=SensorKey.OS_NAME),
            ],
        ),
        SensorCommand(
            "uname -r",
            sensors=[
                TextSensor(key=SensorKey.OS_VERSION),
            ],
        ),
        SensorCommand(
            '(. /etc/os-release && echo "$PRETTY_NAME")',
            sensors=[
                TextSensor(key=SensorKey.OS_RELEASE),
            ],
        ),
        SensorCommand(
            'x=$(/sbin/dmidecode -t system 2>/dev/null) && awk -F ": " \''
            "/Product Name:/ {a=$2} "
            "/Version:/ {b=$2} "
            "/Manufacturer:/ {c=$2} "
            "/Serial Number:/ {d=$2} "
            'END {print a"\\n"b"\\n"c"\\n"d}\' <<<$x',
            sensors=[
                TextSensor(key=SensorKey.DEVICE_NAME),
                TextSensor(key=SensorKey.DEVICE_MODEL),
                TextSensor(key=SensorKey.MANUFACTURER),
                TextSensor(key=SensorKey.SERIAL_NUMBER),
            ],
        ),
        SensorCommand(
            'x=$(cat /proc/cpuinfo) && awk -F ": " \''
            "/^model name/ {a=$2} "
            "/^processor/ {b=$2+1} "
            "/^Hardware/ {c=$2} "
            "/^Model/ {d=$2} "
            'END {print a"\\n"b"\\n"c"\\n"d}\' <<<$x',
            sensors=[
                TextSensor(key=SensorKey.CPU_NAME),
                NumberSensor(key=SensorKey.CPU_CORES),
                TextSensor(key=SensorKey.CPU_HARDWARE),
                TextSensor(key=SensorKey.CPU_MODEL),
            ],
        ),
        SensorCommand(
            "x=$(free -k) && awk '/^Mem:/ {print $2}' <<<$x",
            sensors=[
                NumberSensor(key=SensorKey.TOTAL_MEMORY, unit="KiB"),
            ],
        ),
        SensorCommand(
            "x=$(free -k) && awk '/^Mem:/ {print $4}' <<<$x",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.FREE_MEMORY, unit="KiB"),
            ],
        ),
        SensorCommand(
            "x=$(df -k) && awk '/^\\/dev\\// {"
            'b=$4; $1=$2=$3=$4=$5=""; '
            'gsub(/^ +/, ""); '
            'print $0"|"b}\' <<<$x',
            interval=60,
            separator="|",
            sensors=[
                NumberSensor(key=SensorKey.FREE_DISK_SPACE, dynamic=True, unit="KiB")
            ],
        ),
        SensorCommand(
            "x=$(vmstat 1 2) && "
            "y=$(awk 'END {print $15}' <<<$x) && "
            "echo $((100-$y))",
            interval=30,
            sensors=[
                NumberSensor(key=SensorKey.CPU_LOAD, unit="%"),
            ],
        ),
        SensorCommand(
            "for x in $(ls -d /sys/class/thermal/thermal_zone*); do "
            "echo $(cat $x/type),$(($(cat $x/temp)/1000)); done",
            interval=60,
            separator=",",
            sensors=[
                NumberSensor(key=SensorKey.TEMPERATURE, dynamic=True, unit="°C"),
            ],
        ),
        SensorCommand(
            "x=$(ps -e) && awk 'END {print NR-1}' <<<$x",
            interval=60,
            sensors=[
                NumberSensor(key=SensorKey.PROCESSES),
            ],
        ),
    ],
)
