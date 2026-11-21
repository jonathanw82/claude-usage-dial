"""Finding Claude Code and the login token it saved on this computer.

- Linux and Windows: ``~/.claude/.credentials.json`` (or ``$CLAUDE_CONFIG_DIR/.credentials.json``).
- macOS: the login Keychain, item "Claude Code-credentials" (read with the built-in ``security``
  tool; macOS asks the user to allow it). Falls back to the file if it isn't in the Keychain.

The token is only read, never written or refreshed: Claude Code refreshes it whenever it runs.
"""

import json
import os
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

KEYCHAIN_SERVICE = "Claude Code-credentials"


class UsageError(Exception):
    """A problem with a message that is safe and useful to show the user."""


def config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def credentials_file():
    return config_dir() / ".credentials.json"


def _system():
    return platform.system()  # "Linux", "Windows", "Darwin"


def _keychain_json(run=subprocess.run):
    """The credentials JSON from the macOS Keychain, or None if it isn't there."""
    try:
        res = run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                  capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 and res.stdout.strip() else None


def _load_credentials(run=subprocess.run):
    """Return (parsed JSON, where it came from). Raises UsageError if not found/unreadable."""
    if _system() == "Darwin":
        raw = _keychain_json(run)
        if raw is not None:
            try:
                return json.loads(raw), "macOS Keychain"
            except ValueError:
                raise UsageError("Could not read the Claude Code login from the Keychain")
    path = credentials_file()
    try:
        return json.loads(path.read_text(encoding="utf-8")), str(path)
    except FileNotFoundError:
        raise UsageError("Not signed in to Claude Code on this computer")
    except (OSError, ValueError):
        raise UsageError("Could not read Claude Code's login file")


def read_token(run=subprocess.run, now=None):
    data, _where = _load_credentials(run)
    try:
        oauth = data["claudeAiOauth"]
        token = oauth["accessToken"]
    except (KeyError, TypeError):
        raise UsageError("Claude Code is signed in with an API key, not a Claude account - "
                         "usage limits only exist for Claude subscriptions")
    expires = oauth.get("expiresAt")
    now = now or datetime.now(timezone.utc)
    if isinstance(expires, (int, float)) and expires / 1000 < now.timestamp():
        raise UsageError("Login expired - open Claude Code once to refresh it")
    return token


def login_status(run=subprocess.run):
    """(ok, message) for the Setup window, without exposing the token."""
    try:
        read_token(run)
    except UsageError as e:
        return False, str(e)
    _data, where = _load_credentials(run)
    return True, f"Signed in (login found in {where})"


def _candidates():
    home = Path.home()
    if _system() == "Windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return [home / ".local" / "bin" / "claude.exe", appdata / "npm" / "claude.cmd",
                home / ".claude" / "local" / "claude.exe"]
    return [home / ".local" / "bin" / "claude", home / ".claude" / "local" / "claude",
            Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude"),
            home / ".npm-global" / "bin" / "claude"]


def find_claude_code():
    """Path to the Claude Code program, or None. Checks PATH and the usual install locations
    (apps started from a desktop menu often have a shorter PATH than a terminal)."""
    found = shutil.which("claude")
    if found:
        return found
    for p in _candidates():
        if p.is_file():
            return str(p)
    return None
