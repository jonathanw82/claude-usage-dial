# Plan: smartwatch-style usage dial

> **Superseded (2026-11-21):** the GTK app this plan describes has been replaced by the Qt version — see `portable-release.md`.

Goal: replace the plain progress-bar window with a polished round dial modelled on the reference
watch face (dark face, teal accents, segmented arcs, a colour-scale bar, a small ring), and give
the top-bar indicator a mini ring icon.

Choices made (2026-11-21):
- **Shape:** a borderless, round, floating widget. The desktop shows around it.
- **Centre:** the session % in big type, with its reset countdown under it.
- **Top bar:** a mini ring icon that fills with the session % and changes colour. The `S x% · W y%` text stays.

## Approach

- Build the dial as an **SVG string** in Python and display it with `GdkPixbuf` (librsvg is already
  installed). This avoids the `python3-gi-cairo` package, which would need another `sudo apt`.
  The app stays stdlib-only.
- Re-render the SVG on each data refresh and on the existing 30 s countdown tick.
- Window: undecorated, RGBA visual, transparent CSS background, skip taskbar, keep above.
  Drag anywhere to move it; Esc or double-click hides it; it remembers its position for the session.
- Render at the monitor's scale factor so it stays sharp on HiDPI.
- Known limitation: without cairo regions, the transparent corners of the square window still
  catch clicks. They're invisible, so this is only a minor annoyance.

### Dial layout (reference element → what it shows)
| Reference | Dial |
|---|---|
| Segmented top arcs (left + right) | **Week %**: 24 segments, lit in proportion |
| Ring with ⚡ at the top | Small Claude-style spark glyph in a ring that shows **session %** |
| "STEPS 15888" + rainbow bar | "SESSION" label + 10-segment green→red bar, lit up to the session % |
| Big "09:00" | **Session %** in big type |
| Small multi-colour ring "106" | Ring showing **Week %**, coloured by threshold |
| Weekday row | Session reset: `resets in 3h 12m · 16:30` |
| Flame + bar "1348" | "WEEK" bar + %, with the weekly reset under it (`Tue 04:00`) |
| Date at bottom | Last-updated time, or an error message in red |

Colours: teal `#3ee6c9` normal, amber at ≥ 75 %, red at ≥ 90 % (same thresholds as now).
When a value is unknown, everything renders dimmed with `–%`.

## Steps

- [x] 1. Add `dial_svg(usage, error, updated, now)` to `claude_usage.py` as a pure function
  - Verify: render to PNG offline with GdkPixbuf at 1 %, 52 %, 80 %, 95 % and in the error state,
    and look at each image. Iterate on the look before touching the GTK code.
- [x] 2. Replace `UsageWindow` with a round `DialWindow` (transparent, borderless, draggable, Esc hides).
      `App.render()` calls its `update()` as before; the menu's "Show window" is unchanged
  - Verify: launch with a clean env and take a screenshot. The corners are transparent, it drags, and Esc hides it.
- [x] 3. Top-bar ring icon: `ring_svg(pct)` written to `~/.cache/claude-usage/ring-<pct>-<colour>.svg`
      and set with `set_icon_full`. Stale files are cleaned up
  - Verify: the icon shows next to the label and changes when the % changes (test with a forced value).
- [x] 4. Update `README.md` and record the SVG-vs-cairo choice in `docs/decisions.md`; run `./install.sh` from a normal terminal
  - Verify: `python3 -m py_compile`. **User** confirms the look on the real desktop.
  - Installed 2026-11-21. Drag and Esc have not been tested by hand yet — **user** to confirm.

## Deviations / notes
- 2026-11-21: Steps 1–3 verified. Offline renders at 1/52/80/95 % and in the error state were checked.
  A live screenshot shows transparent corners and real data. The top-bar ring was checked at a low real value (teal) and at a forced 80 % (amber).
- Deviation: the plan said GdkPixbuf. That was soft at 2× scale, so the dial uses `Gio.BytesIcon` instead (see decisions.md).
- Added beyond the plan: right-click opens the menu, R/F5 refreshes, and the tooltip shows the updated time.
- 2026-11-21 (follow-up): Dial is now resizable by dragging its rim (aspect locked, 180–1200 px). It uses a
  `Gtk.Layout` so the window can shrink. Checked by resizing in code to 240 and 600 px. Dragging by hand hasn't been tested yet.
  The divider lines are clipped to r=178 so they no longer run into the bezel.
- 2026-11-21 (follow-up 2): Layout reworked so every element sits inside a safe radius of ~170. The SESSION row is
  centred, the weekly reset time moved into the small ring, the old bottom text was replaced by "↻ updated" time, and the
  dividers fade at their ends. Sharp at large sizes: the SVG is rendered at device px with a debounced re-render.
  Fixed a clipping bug: the image size had been set inside size-allocate, so a single resize left the image stale.
  Verified with a live 600 px screenshot at 2× scale.
- 2026-11-21 (follow-up 3): Size, position and always-on-top are saved to `~/.config/claude-usage/window.json`
  (debounced 0.5 s, atomic write). A position that is no longer on any monitor is ignored. "Always on top" is now
  a menu toggle (default on). Verified: move/resize → quit → relaunch restores the same position @ 480 px, and xprop
  shows `_NET_WM_STATE_ABOVE`, which goes away when the toggle is unticked.
