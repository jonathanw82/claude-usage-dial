"""Start-at-login, per OS. Each function takes optional overrides so it can be unit-tested.

- Linux:   ~/.config/autostart/claude-usage-dial.desktop
- Windows: HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run, value "ClaudeUsageDial"
- macOS:   ~/Library/LaunchAgents/com.claude-usage-dial.plist
"""

import os
import platform
import plistlib
import shlex
import sys
from pathlib import Path

NAME = "claude-usage-dial"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ClaudeUsageDial"
MAC_LABEL = "com.claude-usage-dial"


def launch_command():
    """The command that starts this app, however it was installed."""
    if os.environ.get("APPIMAGE"):           # Linux AppImage: the .AppImage file itself
        return [os.environ["APPIMAGE"]]
    if getattr(sys, "frozen", False):        # PyInstaller build (.exe / .app / binary)
        return [sys.executable]
    return [sys.executable, "-m", "claude_usage"]  # running from source


def _linux_file():
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "autostart" / f"{NAME}.desktop"


def _mac_file():
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def _winreg():
    import winreg  # Windows only
    return winreg


def is_enabled(system=None):
    system = system or platform.system()
    if system == "Windows":
        winreg = _winreg()
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except OSError:
            return False
    return (_mac_file() if system == "Darwin" else _linux_file()).exists()


def set_enabled(on, system=None, command=None):
    """Turn start-at-login on or off. Raises OSError if the OS refuses."""
    system = system or platform.system()
    cmd = command or launch_command()
    if system == "Windows":
        winreg = _winreg()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  " ".join(f'"{c}"' for c in cmd))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return
    path = _mac_file() if system == "Darwin" else _linux_file()
    if not on:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if system == "Darwin":
        path.write_bytes(plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": cmd,
                                         "RunAtLoad": True}))
    else:
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Claude Usage Dial\n"
            "Comment=Shows your Claude session and weekly usage\n"
            f"Exec={shlex.join(cmd)}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")
