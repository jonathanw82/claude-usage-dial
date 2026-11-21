import subprocess

import pytest

from claude_usage import launcher


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData" / "Roaming"))
    return tmp_path


def test_supported_and_labels():
    assert launcher.supported("Linux") and launcher.supported("Windows")
    assert not launcher.supported("Darwin")
    assert "Start menu" in launcher.label("Windows")
    assert "app menu" in launcher.label("Linux")


def test_linux_entry_with_icon(home):
    cmd = ["/home/u/Apps/Claude Usage.AppImage"]
    launcher.install("Linux", cmd)
    desktop = home / ".local/share/applications/claude-usage-dial.desktop"
    icon = home / ".local/share/icons/claude-usage-dial.png"
    text = desktop.read_text()
    assert "Exec='/home/u/Apps/Claude Usage.AppImage'" in text
    assert f"Icon={icon}" in text and icon.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert launcher.is_installed("Linux")
    launcher.install("Linux", ["/new/place.AppImage"])  # moved: entry is rewritten
    assert "Exec=/new/place.AppImage" in desktop.read_text()
    launcher.remove("Linux")
    assert not desktop.exists() and not icon.exists() and not launcher.is_installed("Linux")


def test_windows_shortcut_via_powershell(home):
    seen = {}

    def fake_run(args, env, **_k):
        seen.update(args=args, env=env)
        lnk = env["CUD_LNK"]
        open(lnk, "w").close()  # pretend PowerShell wrote it
        return subprocess.CompletedProcess(args, 0, "", "")

    launcher.install("Windows", [r"C:\Apps\claude-usage-dial.exe"], run=fake_run)
    assert seen["args"][0] == "powershell"
    assert seen["env"]["CUD_TARGET"] == r"C:\Apps\claude-usage-dial.exe"
    assert seen["env"]["CUD_LNK"].endswith("Start Menu/Programs/Claude Usage Dial.lnk".replace(
        "/", launcher.os.sep))
    assert launcher.is_installed("Windows")
    launcher.remove("Windows")
    assert not launcher.is_installed("Windows")


def test_windows_failure_is_reported(home):
    def failing(args, **_k):
        return subprocess.CompletedProcess(args, 1, "", "COM blocked by policy")

    with pytest.raises(OSError, match="COM blocked"):
        launcher.install("Windows", ["x.exe"], run=failing)


def test_macos_is_a_no_op(home):
    launcher.install("Darwin", ["/Applications/X.app/Contents/MacOS/x"])
    assert not launcher.is_installed("Darwin")
