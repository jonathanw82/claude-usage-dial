"""Platform-independent core: reading the Claude Code login, fetching usage, and drawing.

Nothing in here imports a GUI toolkit, so it can be unit-tested and reused by any front end.
"""

import html
import json
import math
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .credentials import UsageError, read_token

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
WARN_PCT = 75
CRIT_PCT = 90


# ---------------------------------------------------------------- data

def parse_usage(body):
    """Turn the endpoint's JSON into {'session': (pct, reset_dt), 'week': (pct, reset_dt)}."""
    if not isinstance(body, dict):
        raise UsageError("Usage endpoint returned an unexpected format")

    def window(key):
        w = body.get(key) or {}
        pct = w.get("utilization")
        reset = w.get("resets_at")
        reset_dt = None
        if isinstance(reset, str):
            try:
                reset_dt = datetime.fromisoformat(reset.replace("Z", "+00:00"))
            except ValueError:
                pass
        try:
            pct = float(pct) if pct is not None else None
        except (TypeError, ValueError):
            pct = None
        return (pct, reset_dt)

    return {"session": window("five_hour"), "week": window("seven_day")}


def fetch_usage(token=None, timeout=20):
    """Fetch and parse current usage. Raises UsageError with a user-facing message."""
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token or read_token()}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-usage-dial",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise UsageError("Login rejected - open Claude Code once to refresh it")
        raise UsageError(f"Usage service returned HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UsageError(f"Network error: {getattr(e, 'reason', e)}")
    except ValueError:
        raise UsageError("Usage service returned invalid data")
    return parse_usage(body)


# ---------------------------------------------------------------- formatting

def fmt_pct(pct):
    return "–%" if pct is None else f"{pct:.0f}%"


def fmt_reset(dt):
    if dt is None:
        return "reset time unknown"
    local = dt.astimezone()
    secs = int((dt - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "resetting now"
    h, m = divmod(secs // 60, 60)
    d, h = divmod(h, 24)
    left = f"{d}d {h}h" if d else (f"{h}h {m:02d}m" if h else f"{m}m")
    when = local.strftime("%H:%M") if d == 0 and local.date() == datetime.now().date() \
        else local.strftime("%a %H:%M")
    return f"resets in {left} ({when})"


# ---------------------------------------------------------------- dial (SVG)

TEAL, AMBER, RED, DIM = "#3ee6c9", "#f5b041", "#ff5a5f", "#4a5557"
SCALE = ["#3ee6c9", "#3ee6c9", "#4fe08a", "#7fdc4f", "#c6e042",
         "#f2d43d", "#f5b041", "#f58a3c", "#f26a45", "#ff5a5f"]
FONT = "Ubuntu"  # bundled (claude_usage/fonts); Qt's SVG renderer ignores font lists
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def level_colour(pct, warn=WARN_PCT, crit=CRIT_PCT):
    if pct is None:
        return DIM
    return RED if pct >= crit else AMBER if pct >= warn else TEAL


def _pt(cx, cy, r, a):
    """Point on a circle; angle in degrees clockwise from 12 o'clock."""
    rad = math.radians(a)
    return cx + r * math.sin(rad), cy - r * math.cos(rad)


def _arc(cx, cy, r, a0, a1):
    if a1 - a0 >= 359.99:  # full circle: two halves
        return _arc(cx, cy, r, a0, a0 + 180) + " " + _arc(cx, cy, r, a0 + 180, a1 - 0.01)
    x0, y0 = _pt(cx, cy, r, a0)
    x1, y1 = _pt(cx, cy, r, a1)
    large = 1 if a1 - a0 > 180 else 0
    return f"M{x0:.2f},{y0:.2f} A{r},{r} 0 {large} 1 {x1:.2f},{y1:.2f}"


def _text(x, y, s, size, fill="#ffffff", anchor="start", weight="normal",
          spacing=0, opacity=1):
    return (f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}" letter-spacing="{spacing}" '
            f'opacity="{opacity}">{html.escape(s)}</text>')


def _wrap(s, width):
    words, lines, cur = s.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    return lines + [cur] if cur else lines


def dial_svg(usage, error=None, updated=None, px=400, warn=WARN_PCT, crit=CRIT_PCT):
    """Return the round watch-face SVG for the usage data.

    Drawn in 400x400 user units; `px` sets the intrinsic pixel size so the SVG is rasterised
    at the size it is shown at (sharp at any size). Everything sits inside a safe radius of
    ~170 so nothing crowds the rim."""
    usage = None if error else usage
    s_pct, s_reset = usage["session"] if usage else (None, None)
    w_pct, w_reset = usage["week"] if usage else (None, None)
    s_col, w_col = level_colour(s_pct, warn, crit), level_colour(w_pct, warn, crit)
    o = []
    add = o.append

    add(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="{px}" height="{px}">')
    add('<defs>'
        '<radialGradient id="face" cx="50%" cy="40%" r="62%">'
        '<stop offset="0" stop-color="#1e2b2d"/><stop offset="1" stop-color="#080b0c"/></radialGradient>'
        '<linearGradient id="bezel" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#4a5054"/><stop offset=".45" stop-color="#121416"/>'
        '<stop offset="1" stop-color="#30353a"/></linearGradient>'
        f'<radialGradient id="core" cx="50%" cy="50%" r="50%">'
        f'<stop offset="0" stop-color="{s_col}" stop-opacity=".32"/>'
        f'<stop offset="1" stop-color="{s_col}" stop-opacity=".04"/></radialGradient>'
        f'<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{TEAL}" stop-opacity="0"/>'
        f'<stop offset=".18" stop-color="{TEAL}" stop-opacity=".6"/>'
        f'<stop offset=".82" stop-color="{TEAL}" stop-opacity=".6"/>'
        f'<stop offset="1" stop-color="{TEAL}" stop-opacity="0"/></linearGradient>'
        '<pattern id="hatch" width="14" height="14" patternUnits="userSpaceOnUse">'
        '<path d="M0,0 L14,14 M14,0 L0,14" stroke="#ffffff" stroke-width=".5" opacity=".045"/></pattern>'
        '<filter id="glow" x="-40%" y="-40%" width="180%" height="180%">'
        '<feGaussianBlur stdDeviation="2.6" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
        '</defs>')

    # bezel + face
    add('<circle cx="200" cy="200" r="198" fill="url(#bezel)"/>')
    add('<circle cx="200" cy="200" r="190" fill="#040506"/>')
    add('<circle cx="200" cy="200" r="184" fill="url(#face)"/>')
    add('<circle cx="200" cy="200" r="184" fill="url(#hatch)"/>')  # (QtSvg ignores clip-path here)
    add('<circle cx="200" cy="200" r="183.5" fill="none" stroke="#ffffff" stroke-opacity=".06"/>')

    # top segmented arcs = week %
    segs, gap = 12, 1.5
    angles = []
    for a0, a1 in ((-60, -18), (18, 60)):
        step = (a1 - a0) / segs
        angles += [(a0 + i * step + gap / 2, a0 + (i + 1) * step - gap / 2) for i in range(segs)]
    lit = round((w_pct or 0) / 100 * len(angles))
    add('<g fill="none" stroke-width="8">')
    for i, (a0, a1) in enumerate(angles):
        add(f'<path d="{_arc(200, 200, 168, a0, a1)}" '
            f'stroke="{w_col if i < lit else "#1a2a2a"}"/>')
    add('</g>')

    # top ring with spark = session %
    cx, cy, r = 200, 78, 28
    add(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#15302b" stroke-width="5"/>')
    if s_pct:
        add(f'<path d="{_arc(cx, cy, r, 0, min(s_pct, 100) * 3.6)}" fill="none" stroke="{s_col}" '
            f'stroke-width="5" stroke-linecap="round" filter="url(#glow)"/>')
    add(f'<circle cx="{cx}" cy="{cy}" r="{r - 6}" fill="url(#core)"/>')
    spark = " ".join(
        f'M{cx + 3.5 * math.sin(math.radians(a)):.2f},{cy - 3.5 * math.cos(math.radians(a)):.2f} '
        f'L{cx + (12 if i % 2 == 0 else 8) * math.sin(math.radians(a)):.2f},'
        f'{cy - (12 if i % 2 == 0 else 8) * math.cos(math.radians(a)):.2f}'
        for i, a in enumerate(range(0, 360, 45)))
    add(f'<path d="{spark}" stroke="{s_col}" stroke-width="3" stroke-linecap="round" '
        f'filter="url(#glow)"/>')

    # SESSION row (centred: badge 54-94, bar 106-346) + colour-scale bar
    add(f'<rect x="54" y="126" width="40" height="28" rx="7" fill="#0b1213" stroke="{TEAL}" '
        f'stroke-width="1.6" stroke-opacity=".85"/>')
    add(_text(74, 145.5, "5H", 13, anchor="middle", weight="bold"))
    add(_text(106, 128, "SESSION", 13, weight="bold", spacing=1.6))
    add(_text(346, 128, fmt_pct(s_pct), 13, fill=s_col, anchor="end", weight="bold"))
    lit = math.ceil((s_pct or 0) / 10 - 1e-9)
    for i in range(10):
        x = 106 + i * 24
        add(f'<path d="M{x + 3.5:.1f},137 h19 l-3.5,13 h-19 z" fill="{SCALE[i]}" '
            f'opacity="{1 if i < lit else 0.13}"/>')
    add('<path d="M40,188 H80 L98,168 H360" fill="none" stroke="url(#fade)" stroke-width="1.6"/>')

    # big session number + countdown (or error)
    num = f"{s_pct:.0f}" if s_pct is not None else "–"
    add(f'<text x="146" y="254" font-family="{FONT}" font-size="86" font-weight="300" '
        f'fill="#ffffff" text-anchor="middle" letter-spacing="-2" '
        f'opacity="{1 if s_pct is not None else .45}">{num}'
        f'<tspan font-size="34" dx="2" fill="{s_col}" letter-spacing="0">%</tspan></text>')
    if error:
        for i, line in enumerate(_wrap(error, 36)[:3]):
            add(_text(200, 284 + i * 14, line, 11.5, fill=RED, anchor="middle"))
    elif s_pct is not None:
        add(_text(146, 279, fmt_reset(s_reset), 11.5, fill="#9aa5a8", anchor="middle"))

    # small segmented ring = week % (+ when it resets)
    cx, cy, r = 298, 224, 33
    add(f'<circle cx="{cx}" cy="{cy}" r="{r + 9}" fill="#0a1011" stroke="#252d30" '
        f'stroke-width="1.5"/>')
    n, a0, span = 12, -135, 270
    lit = round((w_pct or 0) / 100 * n)
    for i in range(n):
        s0, s1 = a0 + i * span / n + 2, a0 + (i + 1) * span / n - 2
        colour = SCALE[min(9, int(i * 10 / n))] if i < lit else "#1e2829"
        add(f'<path d="{_arc(cx, cy, r, s0, s1)}" fill="none" stroke="{colour}" stroke-width="7"/>')
    add(_text(cx, cy - 9, "WEEK", 7.5, fill=w_col, anchor="middle", weight="bold", spacing=1))
    add(_text(cx, cy + 7, fmt_pct(w_pct), 16, anchor="middle", weight="bold"))
    if w_reset and w_pct is not None:
        add(_text(cx, cy + 19, w_reset.astimezone().strftime("%a %H:%M"), 7, fill="#8a9598",
                  anchor="middle"))

    # weekday row: highlight the day the weekly limit resets
    if not error:
        reset_day = w_reset.astimezone().weekday() if w_reset else None
        for i, d in enumerate(DAYS):
            on = i == reset_day
            add(_text(92 + i * 36, 306, d, 11.5, fill=w_col if on else "#6f7a7d",
                      anchor="middle", weight="bold" if on else "normal", spacing=.5))
    # a thin rect, not a path: a flat path has no height, so the fade gradient wouldn't render
    add('<rect x="90" y="318.2" width="220" height="1.6" fill="url(#fade)"/>')

    # week bar row (inside the safe radius at this height: x 110-290)
    add(_text(116, 344, "WEEK", 9.5, fill="#8a9598", weight="bold", spacing=1))
    add('<rect x="156" y="337" width="90" height="7" rx="3.5" fill="#1a2828"/>')
    if w_pct:
        add(f'<rect x="156" y="337" width="{max(7, 90 * min(w_pct, 100) / 100):.1f}" height="7" '
            f'rx="3.5" fill="{w_col}" filter="url(#glow)"/>')
    add(_text(252, 344.5, fmt_pct(w_pct), 12, fill=w_col, weight="bold"))

    # last update
    if updated and not error:
        add(_text(200, 364, f"↻ {updated:%H:%M}", 9, fill=TEAL, anchor="middle", opacity=.6))

    add('</svg>')
    return "".join(o)


def ring_svg(pct, px=64, warn=WARN_PCT, crit=CRIT_PCT):
    """Tray icon: a ring filled to pct with the number drawn inside (tray icons can't show text)."""
    col = level_colour(pct, warn, crit)
    arc = ""
    if pct:
        arc = (f'<path d="{_arc(32, 32, 26, 0, min(pct, 100) * 3.6)}" fill="none" stroke="{col}" '
               f'stroke-width="8" stroke-linecap="round"/>')
    label = "–" if pct is None else str(min(round(pct), 100))
    size = 26 if len(label) <= 2 else 19
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{px}" height="{px}">'
            '<circle cx="32" cy="32" r="30" fill="#0b1112"/>'
            '<circle cx="32" cy="32" r="26" fill="none" stroke="#ffffff" stroke-opacity=".22" '
            f'stroke-width="8"/>{arc}'
            f'<text x="32" y="{32 + size * 0.36:.1f}" font-family="{FONT}" font-size="{size}" '
            f'font-weight="bold" fill="#ffffff" text-anchor="middle">{label}</text></svg>')
