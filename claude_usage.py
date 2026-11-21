#!/usr/bin/env python3
"""Claude usage indicator for the Ubuntu top bar.

Shows the current 5-hour session % and the 7-day (weekly) % used, as reported
by Anthropic's usage endpoint, using the Claude Code login token stored in
~/.claude/.credentials.json. The token is only ever sent to api.anthropic.com.
"""

import html
import json
import math
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import AyatanaAppIndicator3 as AppIndicator  # noqa: E402
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
ICON_DIR = Path.home() / ".cache" / "claude-usage"
SETTINGS = Path.home() / ".config" / "claude-usage" / "window.json"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
REFRESH_SECONDS = 300
WARN_PCT = 75
CRIT_PCT = 90


# ---------------------------------------------------------------- data

class UsageError(Exception):
    pass


def read_token():
    try:
        data = json.loads(CREDENTIALS.read_text())
        oauth = data["claudeAiOauth"]
        token = oauth["accessToken"]
    except FileNotFoundError:
        raise UsageError("Not logged in: ~/.claude/.credentials.json not found")
    except (KeyError, ValueError):
        raise UsageError("Could not read token from credentials file")
    expires = oauth.get("expiresAt")
    if expires and expires / 1000 < datetime.now(timezone.utc).timestamp():
        raise UsageError("Login token expired - run any `claude` command to refresh it")
    return token


def fetch_usage():
    """Return {'session': (pct, reset_dt), 'week': (pct, reset_dt)}."""
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {read_token()}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-usage-indicator/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise UsageError("Token rejected - run any `claude` command to refresh it")
        raise UsageError(f"Usage endpoint returned HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise UsageError(f"Network error: {getattr(e, 'reason', e)}")
    except ValueError:
        raise UsageError("Usage endpoint returned invalid JSON")

    def window(key):
        w = body.get(key) or {}
        pct = w.get("utilization")
        reset = w.get("resets_at")
        reset_dt = None
        if reset:
            try:
                reset_dt = datetime.fromisoformat(reset.replace("Z", "+00:00"))
            except ValueError:
                pass
        return (float(pct) if pct is not None else None, reset_dt)

    return {"session": window("five_hour"), "week": window("seven_day")}


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
FONT = "Ubuntu, 'DejaVu Sans', sans-serif"
DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def level_colour(pct):
    if pct is None:
        return DIM
    return RED if pct >= CRIT_PCT else AMBER if pct >= WARN_PCT else TEAL


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


def dial_svg(usage, error=None, updated=None, px=400):
    """Return the round watch-face SVG for the usage data.

    Drawn in 400x400 user units; `px` sets the intrinsic pixel size so the SVG is rasterised
    at the size it is shown at (sharp at any size). Everything sits inside a safe radius of
    ~170 so nothing crowds the rim."""
    usage = None if error else usage
    s_pct, s_reset = usage["session"] if usage else (None, None)
    w_pct, w_reset = usage["week"] if usage else (None, None)
    s_col, w_col = level_colour(s_pct), level_colour(w_pct)
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
        '<clipPath id="faceclip"><circle cx="200" cy="200" r="184"/></clipPath>'
        '</defs>')

    # bezel + face
    add('<circle cx="200" cy="200" r="198" fill="url(#bezel)"/>')
    add('<circle cx="200" cy="200" r="190" fill="#040506"/>')
    add('<circle cx="200" cy="200" r="184" fill="url(#face)"/>')
    add('<rect width="400" height="400" fill="url(#hatch)" clip-path="url(#faceclip)"/>')
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
    add('<rect x="90" y="318.2" width="220" height="1.6" fill="url(#fade)"/>')  # flat line: a path has no height for the gradient

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


def ring_svg(pct):
    """Small top-bar icon: a ring filled to pct, coloured by level."""
    col = level_colour(pct)
    arc = ""
    if pct:
        arc = (f'<path d="{_arc(11, 11, 8, 0, min(pct, 100) * 3.6)}" fill="none" stroke="{col}" '
               f'stroke-width="3" stroke-linecap="round"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 22 22" width="22" height="22">'
            '<circle cx="11" cy="11" r="8" fill="none" stroke="#ffffff" stroke-opacity=".25" '
            f'stroke-width="3"/>{arc}<circle cx="11" cy="11" r="2.4" fill="{col}"/></svg>')


def ring_icon_path(pct):
    """Write the ring icon to a file named by its content (so the shell reloads it when it
    changes), remove stale ones, and return the path."""
    name = f"ring-{'none' if pct is None else round(pct)}-{level_colour(pct)[1:]}.svg"
    path = ICON_DIR / name
    try:
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(ring_svg(pct))
        for old in ICON_DIR.glob("ring-*.svg"):
            if old != path:
                old.unlink(missing_ok=True)
    except OSError:
        return None
    return str(path)


# ---------------------------------------------------------------- settings

def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(SETTINGS)  # atomic, so a crash mid-write can't corrupt it
    except OSError:
        pass


# ---------------------------------------------------------------- window

DIAL_SIZE = 360               # starting size (px); resizable between the two limits below
DIAL_MIN, DIAL_MAX = 180, 1200
RIM = 0.88                    # pointer this far out from the centre (fraction of radius) = resize
CSS = b"window.dial, window.dial * { background-color: transparent; }"

# (edge, cursor) for each 45-degree sector, clockwise from 12 o'clock
_RIM_EDGES = [
    (Gdk.WindowEdge.NORTH, "n-resize"), (Gdk.WindowEdge.NORTH_EAST, "ne-resize"),
    (Gdk.WindowEdge.EAST, "e-resize"), (Gdk.WindowEdge.SOUTH_EAST, "se-resize"),
    (Gdk.WindowEdge.SOUTH, "s-resize"), (Gdk.WindowEdge.SOUTH_WEST, "sw-resize"),
    (Gdk.WindowEdge.WEST, "w-resize"), (Gdk.WindowEdge.NORTH_WEST, "nw-resize"),
]


class DialWindow(Gtk.Window):
    """Borderless round widget. Drag the face to move it and drag the rim to resize it (it stays round).
    Double-click or Esc hides it, right-click opens the indicator menu, and R/F5 refreshes."""

    def __init__(self, app):
        super().__init__(title="Claude usage")
        self.app = app
        st = load_settings()
        try:
            self.size = max(DIAL_MIN, min(DIAL_MAX, int(st.get("size", DIAL_SIZE))))
        except (TypeError, ValueError):
            self.size = DIAL_SIZE
        self.pos = self._valid_pos(st.get("x"), st.get("y"))
        self.on_top = bool(st.get("on_top", True))
        self._save_id = 0
        self.data = (None, None, None)   # (usage, error, updated) last shown
        self._rerender_id = 0
        self.set_decorated(False)
        self.set_keep_above(self.on_top)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_icon_name("utilities-system-monitor")
        self.set_default_size(self.size, self.size)
        if self.pos:
            self.move(*self.pos)
        geom = Gdk.Geometry()
        geom.min_width = geom.min_height = DIAL_MIN
        geom.max_width = geom.max_height = DIAL_MAX
        geom.min_aspect = geom.max_aspect = 1.0
        self.set_geometry_hints(None, geom, Gdk.WindowHints.MIN_SIZE
                                | Gdk.WindowHints.MAX_SIZE | Gdk.WindowHints.ASPECT)
        self.get_style_context().add_class("dial")
        visual = self.get_screen().get_rgba_visual()
        if visual is not None:  # needs a compositor, which GNOME always has
            self.set_visual(visual)
        self.set_app_paintable(True)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # The image sits in a Gtk.Layout, which requests no size of its own, so the window can
        # shrink as well as grow; the image is then scaled to whatever size the window gets.
        self.image = Gtk.Image()
        self.image.set_pixel_size(self.size)
        layout = Gtk.Layout()
        layout.put(self.image, 0, 0)
        box = Gtk.EventBox(visible_window=False, above_child=True)
        box.add(layout)
        box.add_events(Gdk.EventMask.POINTER_MOTION_MASK)
        box.connect("button-press-event", self._on_button)
        box.connect("motion-notify-event", self._on_motion)
        box.connect("leave-notify-event", lambda w, _e: self._set_cursor(w, None))
        self.add(box)
        self.connect("size-allocate", self._on_size)
        self.connect("configure-event", self._on_configure)
        self.connect("key-press-event", self._on_key)
        self.connect("delete-event", lambda *_: self.hide() or True)
        box.show_all()

    def _rim_edge(self, widget, x, y):
        """(edge, cursor) if (x, y) is on the dial's rim, else None."""
        alloc = widget.get_allocation()
        r = min(alloc.width, alloc.height) / 2
        dx, dy = x - r, y - r
        if math.hypot(dx, dy) < r * RIM:
            return None
        angle = math.degrees(math.atan2(dx, -dy)) % 360
        return _RIM_EDGES[int((angle + 22.5) // 45) % 8]

    def _set_cursor(self, widget, name):
        gdk_win = widget.get_window()
        if gdk_win is not None:
            gdk_win.set_cursor(
                Gdk.Cursor.new_from_name(widget.get_display(), name) if name else None)

    def _on_motion(self, widget, ev):
        rim = self._rim_edge(widget, ev.x, ev.y)
        self._set_cursor(widget, rim[1] if rim else None)
        return False

    def _on_button(self, widget, ev):
        if ev.type == Gdk.EventType._2BUTTON_PRESS:
            self.hide()
        elif ev.button == 1:
            rim = self._rim_edge(widget, ev.x, ev.y)
            x, y = int(ev.x_root), int(ev.y_root)
            if rim:
                self.begin_resize_drag(rim[0], ev.button, x, y, ev.time)
            else:
                self.begin_move_drag(ev.button, x, y, ev.time)
        elif ev.button == 3:
            self.app.menu.popup_at_pointer(ev)
        return True

    def _on_size(self, _w, alloc):
        size = max(DIAL_MIN, min(alloc.width, alloc.height))
        if size != self.size:
            self.size = size
            # Changing the image size inside an allocation pass doesn't take effect until the
            # next one, so do it just after: a quick stretch while dragging...
            GLib.idle_add(lambda: self.image.set_pixel_size(self.size) and False)
            if self._rerender_id:
                GLib.source_remove(self._rerender_id)
            self._rerender_id = GLib.timeout_add(150, self._rerender)  # ...sharp once settled

    def _rerender(self):
        self._rerender_id = 0
        self._draw()
        return False

    # -- remembering size, position and always-on-top (~/.config/claude-usage/window.json)

    def _valid_pos(self, x, y):
        """Saved position, if it is still on a connected monitor (else let the WM place it)."""
        if not isinstance(x, int) or not isinstance(y, int):
            return None
        cx, cy = x + self.size // 2, y + self.size // 2
        display = Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            g = display.get_monitor(i).get_geometry()
            if g.x <= cx < g.x + g.width and g.y <= cy < g.y + g.height:
                return (x, y)
        return None

    def _on_configure(self, _w, _ev):
        if self.get_visible():
            self.pos = tuple(self.get_position())
            if self._save_id:
                GLib.source_remove(self._save_id)
            self._save_id = GLib.timeout_add(500, self.save)
        return False

    def save(self):
        self._save_id = 0
        data = {"size": self.size, "on_top": self.on_top}
        if self.pos:
            data["x"], data["y"] = self.pos
        save_settings(data)
        return False

    def set_on_top(self, on):
        self.on_top = on
        self.set_keep_above(on)
        self.save()

    def show_dial(self):
        if self.pos and not self.get_visible():
            self.move(*self.pos)
        self.set_keep_above(self.on_top)
        self.present()

    def _on_key(self, _w, ev):
        if ev.keyval == Gdk.KEY_Escape:
            self.hide()
        elif ev.keyval in (Gdk.KEY_r, Gdk.KEY_F5):
            self.app.refresh()
        return True

    def update(self, usage, error, updated):
        self.data = (usage, error, updated)
        self._draw()
        when = f"Updated {updated:%H:%M:%S}" if updated else "Loading…"
        self.set_tooltip_text(error or when)

    def _draw(self):
        # The SVG's intrinsic size is set to the real device pixels (window size x HiDPI
        # scale), and it's shown as a GIcon so GTK maps it 1:1 onto the screen: sharp at any size.
        usage, error, updated = self.data
        px = self.size * self.get_scale_factor()
        svg = dial_svg(usage, error, updated, px=px)
        self.image.set_from_gicon(Gio.BytesIcon.new(GLib.Bytes.new(svg.encode())),
                                  Gtk.IconSize.DIALOG)
        self.image.set_pixel_size(self.size)


# ---------------------------------------------------------------- indicator

class App:
    def __init__(self):
        self.usage = None
        self.error = None
        self.updated = None
        self.busy = False

        self.ind = AppIndicator.Indicator.new(
            "claude-usage", "utilities-system-monitor",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS)
        self.ind.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.ind.set_label("S …  W …", "S 100% · W 100%")

        menu = Gtk.Menu()
        self.mi_session = Gtk.MenuItem(label="Session: …")
        self.mi_week = Gtk.MenuItem(label="Week: …")
        self.mi_status = Gtk.MenuItem(label="Loading…")
        for mi in (self.mi_session, self.mi_week, self.mi_status):
            mi.set_sensitive(False)
            menu.append(mi)
        menu.append(Gtk.SeparatorMenuItem())
        show = Gtk.MenuItem(label="Show window")
        show.connect("activate", lambda *_: self.window.show_dial())
        refresh = Gtk.MenuItem(label="Refresh now")
        refresh.connect("activate", lambda *_: self.refresh())
        self.mi_on_top = Gtk.CheckMenuItem(label="Always on top")
        self.mi_on_top.connect("toggled", lambda mi: self.window.set_on_top(mi.get_active()))
        quit_ = Gtk.MenuItem(label="Quit")
        quit_.connect("activate", lambda *_: (self.window.save(), Gtk.main_quit()))
        for mi in (show, self.mi_on_top, refresh, quit_):
            menu.append(mi)
        menu.show_all()
        self.ind.set_menu(menu)
        self.menu = menu
        self.ind.set_secondary_activate_target(show)  # middle-click opens window

        self.window = DialWindow(self)
        self.mi_on_top.set_active(self.window.on_top)
        self.refresh()
        GLib.timeout_add_seconds(REFRESH_SECONDS, self._tick)
        GLib.timeout_add_seconds(30, self._redraw_countdowns)

    def _tick(self):
        self.refresh()
        return True

    def _redraw_countdowns(self):
        self.render()
        return True

    def refresh(self):
        if self.busy:
            return
        self.busy = True

        def work():
            try:
                usage, error = fetch_usage(), None
            except UsageError as e:
                usage, error = None, str(e)
            except Exception as e:  # never let the background thread die silently
                usage, error = None, f"Unexpected error: {e}"
            GLib.idle_add(self._done, usage, error)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, usage, error):
        self.busy = False
        self.error = error
        if usage:
            self.usage = usage
            self.updated = datetime.now()
        self.render()
        return False

    def render(self):
        usage = None if self.error else self.usage
        s_pct, s_reset = usage["session"] if usage else (None, None)
        w_pct, w_reset = usage["week"] if usage else (None, None)
        self.ind.set_label(f"S {fmt_pct(s_pct)} · W {fmt_pct(w_pct)}", "S 100% · W 100%")
        icon = ring_icon_path(s_pct)
        if icon:
            self.ind.set_icon_full(icon, f"Session {fmt_pct(s_pct)}")
        self.mi_session.set_label(f"Session: {fmt_pct(s_pct)} — {fmt_reset(s_reset)}")
        self.mi_week.set_label(f"Week: {fmt_pct(w_pct)} — {fmt_reset(w_reset)}")
        self.mi_status.set_label(self.error or (
            f"Updated {self.updated:%H:%M:%S}" if self.updated else "Loading…"))
        self.window.update(usage, self.error, self.updated)


def main():
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    App()
    Gtk.main()


if __name__ == "__main__":
    main()
