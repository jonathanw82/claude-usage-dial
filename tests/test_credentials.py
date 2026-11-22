import json
import subprocess
from datetime import datetime, timezone

import pytest

from claude_usage import credentials as cr
from claude_usage.credentials import UsageError

FUTURE_MS = 4_000_000_000_000  # year 2096
GOOD = {"claudeAiOauth": {"accessToken": "tok-123", "expiresAt": FUTURE_MS}}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(cr.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(cr, "_system", lambda: "Linux")
    return tmp_path


def write_creds(dir_, data):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / ".credentials.json").write_text(json.dumps(data))


def no_keychain(*_a, **_k):
    return subprocess.CompletedProcess([], 44, "", "not found")


def test_reads_token_from_file(home):
    write_creds(home / ".claude", GOOD)
    assert cr.read_token() == "tok-123"


def test_respects_claude_config_dir(home, monkeypatch):
    write_creds(home / "custom", GOOD)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "custom"))
    assert cr.read_token() == "tok-123"


def test_missing_file_means_not_signed_in(home):
    with pytest.raises(UsageError, match="Not signed in"):
        cr.read_token()


def test_corrupt_file(home):
    (home / ".claude").mkdir()
    (home / ".claude" / ".credentials.json").write_text("{nope")
    with pytest.raises(UsageError, match="Could not read"):
        cr.read_token()


def test_api_key_login_is_explained(home):
    write_creds(home / ".claude", {"primaryApiKey": "x"})
    with pytest.raises(UsageError, match="API key"):
        cr.read_token()


def test_expired_token_is_its_own_error(home):
    write_creds(home / ".claude", {"claudeAiOauth": {"accessToken": "t", "expiresAt": 1000}})
    with pytest.raises(cr.LoginExpired, match="expired"):
        cr.read_token(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    st = cr.login_status(now=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert (st.ok, st.expired) == (False, True)


def test_not_signed_in_is_not_expired(home):
    st = cr.login_status()
    assert (st.ok, st.expired) == (False, False) and "Not signed in" in st.message


def test_macos_reads_keychain_first(home, monkeypatch):
    monkeypatch.setattr(cr, "_system", lambda: "Darwin")
    calls = []

    def fake_security(cmd, **_k):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, json.dumps(GOOD) + "\n", "")

    assert cr.read_token(run=fake_security) == "tok-123"
    assert calls[0][:2] == ["security", "find-generic-password"]
    assert "Claude Code-credentials" in calls[0]


def test_macos_falls_back_to_file(home, monkeypatch):
    monkeypatch.setattr(cr, "_system", lambda: "Darwin")
    write_creds(home / ".claude", GOOD)
    assert cr.read_token(run=no_keychain) == "tok-123"


def test_login_status_never_contains_token(home):
    write_creds(home / ".claude", GOOD)
    st = cr.login_status()
    assert st.ok and not st.expired and "tok-123" not in st.message


def test_find_claude_code_checks_usual_places(home, monkeypatch):
    monkeypatch.setattr(cr.shutil, "which", lambda _n: None)
    assert cr.find_claude_code() is None
    exe = home / ".local" / "bin" / "claude"
    exe.parent.mkdir(parents=True)
    exe.write_text("")
    assert cr.find_claude_code() == str(exe)
