import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

from claude_usage import core
from claude_usage.credentials import UsageError

# Shape of the real response, trimmed (verified against the live endpoint 2026-11-21).
SAMPLE = {
    "five_hour": {"utilization": 1.0, "resets_at": "2026-11-21T16:30:00.288052+00:00",
                  "limit_dollars": None},
    "seven_day": {"utilization": 52.0, "resets_at": "2026-11-24T04:00:00.288071+00:00"},
    "seven_day_opus": None,
    "extra_usage": {},
}


def test_parse_usage_reads_both_windows():
    u = core.parse_usage(SAMPLE)
    assert u["session"][0] == 1.0
    assert u["week"][0] == 52.0
    assert u["session"][1] == datetime(2026, 11, 21, 16, 30, 0, 288052, tzinfo=timezone.utc)


def test_parse_usage_tolerates_missing_and_bad_fields():
    u = core.parse_usage({"five_hour": {"utilization": "oops", "resets_at": "not a date"}})
    assert u == {"session": (None, None), "week": (None, None)}


def test_parse_usage_rejects_non_object():
    with pytest.raises(UsageError):
        core.parse_usage(["nope"])


@pytest.mark.parametrize("pct,expected", [(None, "–%"), (0, "0%"), (52.4, "52%"), (99.6, "100%")])
def test_fmt_pct(pct, expected):
    assert core.fmt_pct(pct) == expected


def test_fmt_reset():
    now = datetime.now(timezone.utc)
    assert core.fmt_reset(None) == "reset time unknown"
    assert core.fmt_reset(now - timedelta(minutes=1)) == "resetting now"
    assert core.fmt_reset(now + timedelta(hours=3, minutes=12, seconds=30)).startswith(
        "resets in 3h 12m")
    assert core.fmt_reset(now + timedelta(days=2, hours=5, seconds=30)).startswith(
        "resets in 2d 5h")


@pytest.mark.parametrize("pct,warn,crit,colour", [
    (None, 75, 90, core.DIM), (10, 75, 90, core.TEAL), (75, 75, 90, core.AMBER),
    (90, 75, 90, core.RED), (60, 50, 70, core.AMBER),
])
def test_level_colour_thresholds(pct, warn, crit, colour):
    assert core.level_colour(pct, warn, crit) == colour


def _usage(s, w):
    now = datetime.now(timezone.utc)
    return {"session": (s, now + timedelta(hours=3)), "week": (w, now + timedelta(days=2))}


@pytest.mark.parametrize("s,w", [(0, 0), (1, 52), (52, 30), (100, 100)])
def test_dial_svg_is_well_formed(s, w):
    svg = core.dial_svg(_usage(s, w), updated=datetime.now(), px=720)
    root = ET.fromstring(svg)
    assert root.get("width") == "720"
    assert f">{s}<" in svg  # big session number


def test_dial_svg_error_state_escapes_message():
    svg = core.dial_svg(None, error="Bad <thing> & more")
    ET.fromstring(svg)
    assert "Bad &lt;thing&gt; &amp; more" in svg


@pytest.mark.parametrize("pct", [None, 0, 6, 80, 100, 140])
def test_ring_svg_is_well_formed(pct):
    ET.fromstring(core.ring_svg(pct))


def test_http_401_means_login_expired(monkeypatch):
    import io
    import urllib.error

    from claude_usage.credentials import LoginExpired

    def reject(*_a, **_k):
        raise urllib.error.HTTPError(core.USAGE_URL, 401, "Unauthorized", {}, io.BytesIO(b""))

    monkeypatch.setattr(core.urllib.request, "urlopen", reject)
    with pytest.raises(LoginExpired, match="renew"):
        core.fetch_usage(token="t")


def test_expired_message_fits_on_the_dial():
    from claude_usage.credentials import LoginExpired
    assert len(core._wrap(str(LoginExpired()), 36)) <= 3  # the dial shows at most 3 lines
