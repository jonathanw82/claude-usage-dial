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
