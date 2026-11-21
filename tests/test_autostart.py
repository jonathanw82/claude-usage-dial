import plistlib
import sys
import types

import pytest

from claude_usage import autostart


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(autostart.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("APPIMAGE", raising=False)
    return tmp_path


def test_linux_desktop_file(home):
    cmd = ["/opt/My Apps/claude-usage-dial.AppImage"]
    assert not autostart.is_enabled("Linux")
    autostart.set_enabled(True, "Linux", cmd)
    f = home / ".config" / "autostart" / "claude-usage-dial.desktop"
    assert "Exec='/opt/My Apps/claude-usage-dial.AppImage'" in f.read_text()
    assert autostart.is_enabled("Linux")
    autostart.set_enabled(False, "Linux", cmd)
    assert not f.exists() and not autostart.is_enabled("Linux")


def test_macos_launch_agent(home):
    cmd = ["/Applications/Claude Usage Dial.app/Contents/MacOS/claude-usage-dial"]
    autostart.set_enabled(True, "Darwin", cmd)
    plist = plistlib.loads((home / "Library/LaunchAgents/com.claude-usage-dial.plist").read_bytes())
    assert plist["ProgramArguments"] == cmd and plist["RunAtLoad"] is True
    assert autostart.is_enabled("Darwin")
    autostart.set_enabled(False, "Darwin", cmd)
    assert not autostart.is_enabled("Darwin")


class FakeWinreg(types.SimpleNamespace):
    """Just enough of winreg for the Run key."""

    def __init__(self):
        super().__init__(HKEY_CURRENT_USER=1, KEY_SET_VALUE=2, REG_SZ=1, values={})

    def OpenKey(self, *_a):
        reg = self

        class Key:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False
        Key.reg = reg
        return Key()

    def QueryValueEx(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        return self.values[name], 1

    def SetValueEx(self, _key, name, _r, _t, value):
        self.values[name] = value

    def DeleteValue(self, _key, name):
        if name not in self.values:
            raise FileNotFoundError
        del self.values[name]


def test_windows_run_key(monkeypatch):
    fake = FakeWinreg()
    monkeypatch.setattr(autostart, "_winreg", lambda: fake)
    assert not autostart.is_enabled("Windows")
    autostart.set_enabled(True, "Windows", [r"C:\Apps\claude-usage-dial.exe"])
    assert fake.values["ClaudeUsageDial"] == r'"C:\Apps\claude-usage-dial.exe"'
    assert autostart.is_enabled("Windows")
    autostart.set_enabled(False, "Windows")
    autostart.set_enabled(False, "Windows")  # already off: no error
    assert not autostart.is_enabled("Windows")


def test_launch_command_variants(monkeypatch):
    assert autostart.launch_command()[1:] == ["-m", "claude_usage"]
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert autostart.launch_command() == [sys.executable]
    monkeypatch.setenv("APPIMAGE", "/home/u/Claude.AppImage")
    assert autostart.launch_command() == ["/home/u/Claude.AppImage"]
