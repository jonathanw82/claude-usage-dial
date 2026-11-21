import pytest

from claude_usage import settings


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "config_dir", lambda: tmp_path / "cfg")
    return tmp_path


def test_defaults_when_missing():
    assert settings.load() == settings.DEFAULTS


def test_round_trip():
    data = settings.load() | {"size": 480, "x": 10, "y": -5, "on_top": False, "warn": 60}
    settings.save(data)
    assert settings.load() == data


def test_bad_values_fall_back_or_clamp():
    settings.save({"size": 99999, "x": "left", "on_top": "yes", "refresh_min": 0})
    got = settings.load()
    assert got["size"] == 1200 and got["x"] is None
    assert got["on_top"] is True and got["refresh_min"] == 1


def test_warn_must_be_below_crit():
    settings.save({"warn": 95, "crit": 90})
    got = settings.load()
    assert (got["warn"], got["crit"]) == (settings.DEFAULTS["warn"], settings.DEFAULTS["crit"])


def test_corrupt_file_gives_defaults(cfg):
    (cfg / "cfg").mkdir()
    (cfg / "cfg" / "settings.json").write_text("{nope")
    assert settings.load() == settings.DEFAULTS


def test_last_cmd_round_trip_and_validation():
    settings.save(settings.load() | {"last_cmd": ["/apps/Claude.AppImage"]})
    assert settings.load()["last_cmd"] == ["/apps/Claude.AppImage"]
    settings.save({"last_cmd": "not-a-list"})
    assert settings.load()["last_cmd"] is None
