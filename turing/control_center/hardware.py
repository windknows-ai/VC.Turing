"""What this PC can run: graphics memory and system memory, for local model advice."""

import ctypes
import winreg

_DISPLAY_CLASS = r"SYSTEM\ControlSet001\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"


def gpus() -> list[tuple[str, float]]:
    """(name, dedicated memory in GB) for each graphics adapter, largest first.

    Read from the registry: WMI's AdapterRAM is a 32-bit field and tops out at 4 GB.
    """
    found = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS)
    except OSError:
        return found
    for i in range(64):
        try:
            sub = winreg.EnumKey(root, i)
        except OSError:
            break
        if not sub.isdigit():
            continue
        try:
            with winreg.OpenKey(root, sub) as k:
                name = winreg.QueryValueEx(k, "DriverDesc")[0]
                try:
                    size = winreg.QueryValueEx(k, "HardwareInformation.qwMemorySize")[0]
                except OSError:
                    raw = winreg.QueryValueEx(k, "HardwareInformation.MemorySize")[0]
                    size = int.from_bytes(raw, "little") if isinstance(raw, bytes) else raw
        except OSError:
            continue
        if size:
            found.append((name, round(int(size) / 2**30, 1)))
    return sorted(found, key=lambda g: -g[1])


class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def ram_gb() -> float:
    status = _MemoryStatus()
    status.dwLength = ctypes.sizeof(status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return round(status.ullTotalPhys / 2**30, 1)


def summary() -> dict:
    cards = gpus()
    name, vram = cards[0] if cards else ("", 0.0)
    return {"gpu": name, "vram_gb": vram, "ram_gb": ram_gb()}
