"""User settings, stored as JSON in the usual per-user config folder for each OS."""

import json
import os
import platform
from pathlib import Path

from .core import CRIT_PCT, WARN_PCT

APP_DIR_NAME = "claude-usage-dial"

DEFAULTS = {
    "size": 360,            # dial size in px
    "x": None,              # dial position (None = let the OS place it)
    "y": None,
    "on_top": True,
    "refresh_min": 5,
    "warn": WARN_PCT,
    "crit": CRIT_PCT,
    "show_dial_at_start": True,
    "setup_seen": False,    # Setup window opens by itself until it has been seen once
    "last_cmd": None,       # how the app was last launched; if it moves, menu/autostart are fixed
}

LIMITS = {"size": (180, 1200), "refresh_min": (1, 60), "warn": (1, 99), "crit": (2, 100)}


def config_dir():
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / APP_DIR_NAME


def settings_file():
    return config_dir() / "settings.json"


def _clean(data):
    """Defaults, overlaid with any valid saved values (bad types/ranges are ignored)."""
    out = dict(DEFAULTS)
    if not isinstance(data, dict):
        return out
    for key, default in DEFAULTS.items():
        val = data.get(key)
        if key == "last_cmd":
            if isinstance(val, list) and all(isinstance(v, str) for v in val):
                out[key] = val
        elif key in ("x", "y"):
            if isinstance(val, int) and not isinstance(val, bool):
                out[key] = val
        elif isinstance(default, bool):
            if isinstance(val, bool):
                out[key] = val
        elif isinstance(val, (int, float)) and not isinstance(val, bool):
            lo, hi = LIMITS[key]
            out[key] = int(min(hi, max(lo, val)))
    if out["warn"] >= out["crit"]:
        out["warn"], out["crit"] = DEFAULTS["warn"], DEFAULTS["crit"]
    return out


def load():
    try:
        return _clean(json.loads(settings_file().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save(data):
    path = settings_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(_clean(data), indent=1), encoding="utf-8")
        tmp.replace(path)  # atomic: a crash mid-write can't corrupt the file
    except OSError:
        pass
