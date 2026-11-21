"""Start-menu / app-menu entry, per OS. Each function takes optional overrides for tests.

- Linux:   ~/.local/share/applications/claude-usage-dial.desktop, icon copied next to it
- Windows: Start Menu\\Programs\\Claude Usage Dial.lnk (made with the built-in WScript.Shell)
- macOS:   not needed - an app in /Applications already shows in Launchpad with its icon
"""

import os
import platform
import shlex
import shutil
import subprocess
from pathlib import Path

from .autostart import launch_command

NAME = "claude-usage-dial"
TITLE = "Claude Usage Dial"
ICON_SRC = Path(__file__).with_name("icon.png")


def supported(system=None):
    return (system or platform.system()) in ("Linux", "Windows")


def label(system=None):
    return "Show in the Start menu" if (system or platform.system()) == "Windows" \
        else "Show in the app menu"


def _data_home():
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))


def _linux_desktop():
    return _data_home() / "applications" / f"{NAME}.desktop"


def _linux_icon():
    return _data_home() / "icons" / f"{NAME}.png"


def _windows_lnk():
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{TITLE}.lnk"


def is_installed(system=None):
    system = system or platform.system()
    if system == "Windows":
        return _windows_lnk().exists()
    if system == "Linux":
        return _linux_desktop().exists()
    return False


# PowerShell reads the paths from environment variables, so no quoting/escaping is needed.
_PS_SCRIPT = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:CUD_LNK); "
              "$s.TargetPath = $env:CUD_TARGET; $s.IconLocation = $env:CUD_TARGET + ',0'; "
              "$s.Description = 'Shows your Claude session and weekly usage'; $s.Save()")


def install(system=None, command=None, run=subprocess.run):
    """Add (or update) the menu entry. Raises OSError if it can't be written."""
    system = system or platform.system()
    cmd = command or launch_command()
    if system == "Windows":
        lnk = _windows_lnk()
        lnk.parent.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, CUD_LNK=str(lnk), CUD_TARGET=cmd[0])
        res = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_SCRIPT],
                  env=env, capture_output=True, text=True, timeout=60,
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if res.returncode != 0:
            raise OSError(f"Couldn't create the Start menu shortcut: {res.stderr.strip()[:200]}")
        return
    if system != "Linux":
        return
    icon, desktop = _linux_icon(), _linux_desktop()
    icon.parent.mkdir(parents=True, exist_ok=True)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ICON_SRC, icon)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={TITLE}\n"
        "Comment=Shows your Claude session and weekly usage\n"
        f"Exec={shlex.join(cmd)}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
        f"StartupWMClass={NAME}\n", encoding="utf-8")


def remove(system=None):
    system = system or platform.system()
    if system == "Windows":
        _windows_lnk().unlink(missing_ok=True)
    elif system == "Linux":
        _linux_desktop().unlink(missing_ok=True)
        _linux_icon().unlink(missing_ok=True)
