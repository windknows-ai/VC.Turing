"""Put a 图灵 shortcut on the desktop and in the Start menu. Run again any time to repair them."""

import sys
from pathlib import Path

import win32com.client

ROOT = Path(__file__).resolve().parent.parent
PYTHONW = Path(sys.executable).with_name("pythonw.exe")
ICON = ROOT / "turing" / "assets" / "turing.ico"


def create(folder: str) -> Path:
    shell = win32com.client.Dispatch("WScript.Shell")
    path = Path(shell.SpecialFolders(folder)) / "图灵.lnk"
    link = shell.CreateShortcut(str(path))
    link.TargetPath = str(PYTHONW)
    link.Arguments = "-m turing.desktop"
    link.WorkingDirectory = str(ROOT)
    link.IconLocation = str(ICON)
    link.Description = "图灵语音助手"
    link.Save()
    return path


if __name__ == "__main__":
    for folder in ("Desktop", "Programs"):
        print(f"Created {create(folder)}")
