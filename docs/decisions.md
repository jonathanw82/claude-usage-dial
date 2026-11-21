# Decisions

## 2026-11-20 — Data source: Anthropic OAuth usage endpoint
- **Decision:** read the Claude Code token from `~/.claude/.credentials.json` and GET
  `https://api.anthropic.com/api/oauth/usage` (header `anthropic-beta: oauth-2025-04-20`). Read-only;
  never refresh or rewrite the credentials file.
- **Why:** it's the same source as `/usage` and gives the real 5h and 7d percentages and reset times.
- **Rejected:** estimating usage from local `~/.claude/projects/*.jsonl` logs (no official limits,
  so % would be guesswork; misses usage from claude.ai/other devices).

## 2026-11-20 — UI: Python + GTK3 + AyatanaAppIndicator3
- **Decision:** single stdlib-only Python script; top-bar label + menu, plus a GTK window.
- **Why:** works with Ubuntu's preinstalled appindicator GNOME extension; no pip/venv needed.
- **Rejected:** GNOME Shell extension (JS, tied to Shell versions, harder to debug);
  Electron/web app (heavy for two numbers).

## 2026-11-21 — Dial drawn as SVG, shown as a GIcon
- **Decision:** build the round dial and the top-bar ring as SVG strings in Python. The window
  shows the dial via `Gio.BytesIcon` in a `Gtk.Image`. The ring is written to `~/.cache/claude-usage/`
  for `set_icon_full`.
- **Why:** no new dependency (librsvg is already present). Loading the SVG as a GIcon makes GTK rasterise it at the
  monitor's scale factor, so it's sharp at 2×. A plain pixbuf was visibly soft.
- **Rejected:** a Cairo `draw` handler (needs `python3-gi-cairo`, another sudo install); GdkPixbuf
  at logical size (blurry on HiDPI).
- **Trade-off:** without cairo regions the window can't get a round input shape, so its invisible
  corners still catch clicks.

## 2026-11-21 — Rasterise the dial at device pixels
- **Decision:** `dial_svg(..., px=size*scale)` sets the SVG's own width/height to the window's real
  device pixels, and it is re-rendered 150 ms after a resize settles.
- **Why:** GTK rasterised the `BytesIcon` at the SVG's intrinsic 400 px and then stretched it, so the dial got soft at
  large sizes. With the intrinsic size matching the screen, the mapping is 1:1.
- **Rejected:** re-rendering on every resize step (librsvg with blur filters at ~1200 px is too
  slow to do on every drag frame).

## 2026-11-21 — Port to Qt (PySide6) + PyInstaller for a portable Linux/Windows/macOS release
- **Decision:** replace the GTK3 + AyatanaAppIndicator front end with PySide6 (QtWidgets, QtSvg,
  QSystemTrayIcon) and ship self-contained builds made by PyInstaller: an AppImage on Linux, a single .exe
  on Windows, and a .app on macOS. These are built by GitHub Actions on `v*` tags. GUI-free logic lives in
  `claude_usage/core.py` and `credentials.py`.
- **Why:** the user wants anyone to download and run it with nothing else installed. GTK and Ayatana can't be
  bundled reliably and don't exist on Windows or macOS. Qt bundles fully on all three OSes. Its tray uses
  StatusNotifierItem over DBus directly, so Linux needs no libappindicator. The dial SVG carries over unchanged.
- **Rejected:** keeping GTK in an AppImage (Linux only); Electron (heavy, and the dial would need rewriting);
  Tauri (needs webkit2gtk on Linux); snap/flatpak (confinement blocks reading `~/.claude` without
  store approval, and flatpak isn't preinstalled on Ubuntu).
- **Trade-offs:** tray icons can't show text, so the session % is drawn into the ring icon. Downloads are about
  130 MB unpacked (the AppImage is compressed). Builds aren't code-signed, so SmartScreen and Gatekeeper warn on first launch.
  Supersedes the 2026-11-20 GTK UI decision and the GIcon/device-pixel notes (Qt renders via `QSvgRenderer`
  at device pixels).

## 2026-11-21 — macOS login from the Keychain; bundled Ubuntu font
- **Decision:** on macOS, read the Keychain item `Claude Code-credentials` with the system `security`
  tool, falling back to `~/.claude/.credentials.json`. Bundle the Ubuntu R/B/L fonts.
- **Why:** Claude Code on macOS stores its login in the Keychain, and `security` needs no extra dependency.
  QtSvg ignores font fallback lists, so without a bundled font the dial would look different on each OS.
- **Unverified:** the Keychain path hasn't been tested on a real Mac.
