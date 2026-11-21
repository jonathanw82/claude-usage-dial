# Plan: portable, downloadable release (Linux, Windows, Mac) + Setup window

Goal: anyone can download one file from GitHub and run the Claude usage dial with nothing else
installed except Claude Code (signed in). Add a Setup window to guide new users.

Choices made (2026-11-21):
- **Platforms:** Linux, Windows and Mac. The UI is ported from GTK to **Qt (PySide6)**, bundled with **PyInstaller**.
- **Distribution:** a public **GitHub repo**. GitHub Actions builds the downloads for each release.
- **Setup window:** a separate window, opened from the tray menu. It opens by itself on first run and whenever data fails.
  It has four sections: requirements check, test connection, preferences and a privacy notice.

## What carries over unchanged
`dial_svg`, `ring_svg`, `fetch_usage`, the formatting helpers and the colours/thresholds: the face you
approved stays exactly the same. Only the GTK window, indicator and installer get replaced.

## Limits we can't bundle away (to state in the README)
- Each user needs **Claude Code installed and signed in**. The app reads its login and does not sign in itself.
- **Tray icon text:** Qt tray icons are images only. The `S x% · W y%` label becomes an icon with the
  session % drawn inside the ring; the tooltip and menu show both numbers.
- **Linux tray:** needs desktop support. Ubuntu has it built in. Plain GNOME on Fedora or Debian needs the
  "AppIndicator" extension. The dial window works either way.
- **Wayland (Linux):** apps can't set their own position or stay above other windows there. On Wayland, the remembered
  position and always-on-top won't apply. Ubuntu's default X11/Xorg session is fine.
- **Unsigned downloads:** Windows SmartScreen and macOS Gatekeeper will warn on first launch
  ("More info → Run anyway", or right-click → Open on Mac). Signing would need paid certificates (Apple $99/yr).
- **Mac login storage:** Claude Code on macOS keeps its token in the Keychain (service
  `Claude Code-credentials`). The app reads it with the `security` tool, and macOS asks the user to allow it once.
  **Unverified**: I have no Mac here, so this needs a Mac user to test.
- The usage endpoint is unofficial and could change.

## Steps (one commit each; tests and lint green before each)

- [x] 0. `git init`, `.gitignore` (`.venv/`, `build/`, `dist/`, `__pycache__/`), commit the current GTK version as a baseline
  - Verify: `git log` shows the baseline commit
- [x] 1. Restructure into a package: `claude_usage/core.py` (no GUI: credentials, fetch, formatting, SVGs),
      `.venv` + `requirements.txt` (pinned PySide6, pytest, ruff, pyinstaller)
  - Verify: `pytest` covers the parser (using a fixture from the real response shape), formatting, and that `dial_svg`
    is well-formed XML at 0/52/100 % and in the error state. `ruff check` is clean.
- [x] 2. Per-OS credentials: file on Linux/Windows (respects `CLAUDE_CONFIG_DIR`), Keychain on macOS
      with a file fallback, plus clear error messages for "Claude Code not installed" and "not signed in"
  - Verify: unit tests with mocked files and a mocked `security` command. A live check on Linux.
- [x] 3. Qt dial window: frameless, translucent, painted with `QSvgRenderer` at device pixels, and **masked
      to a circle** (fixes the corners catching clicks). Drag to move, rim-resize, double-click/Esc to hide, right-click menu,
      size/position/on-top remembered (JSON in the OS config dir)
  - Verify: run from `.venv` on this machine and take screenshots at 360 and 600 px. Check that position and size persist.
- [x] 4. Tray icon + menu: a ring with the session % drawn in, both numbers in the tooltip, and the menu: Show dial /
      Setup… / Always on top / Refresh / Quit
  - Verify: screenshot of the Ubuntu top bar at the real % and at a forced 80 %
- [x] 5. Setup window:
      - **Requirements:** ✓/✗ for Claude Code found and signed in, each with the fix spelled out, and a Re-check button
      - **Test connection:** fetches once and shows the result or a plain-English error
      - **Preferences:** start at login (Linux autostart `.desktop`, Windows `HKCU\…\Run`, macOS
        LaunchAgent), refresh interval, amber/red thresholds, always on top, show dial at startup
      - **Privacy notice**
      - Opens automatically on first run and on fetch errors (at most once per error, so it doesn't nag)
  - Verify: screenshots of each state on Linux (renaming the credentials file for the ✗ state, then restoring it). Each start-at-login
    writer is unit-tested.
- [x] 6. Packaging: PyInstaller spec (only the Qt modules needed, to keep it small) and a `--self-test` flag
      (renders the dial offscreen and exits 0). GitHub Actions on tag `v*`: Linux **AppImage** (built on
      Ubuntu 22.04 for wide compatibility), Windows **.exe**, macOS **.app** in a zip, all attached to the Release
  - Verify: build the AppImage locally and run it with a clean environment on this machine. CI runs `--self-test` on all three OSes.
    Real Windows/Mac testing needs someone with those machines. **This is a gap I can't close from here.**
- [x] 7. Docs: rewrite the README for end users (download, first run, the warnings above, uninstall), add a LICENSE,
      update `docs/decisions.md` (GTK→Qt, PyInstaller, per-OS credentials), and remove the GTK script and `install.sh`
  - Verify: follow the README from scratch using the built AppImage
- [x] 8. **User confirms**, then create the public GitHub repo, push, and tag `v0.1.0` to trigger the first release build
  - Verify: the Release page has three downloads; download the Linux one and run it

## Open questions (answer before step 7)
- **License:** MIT (anyone can use and modify it, with credit) is my suggestion.
- **Repo name and app name:** e.g. `claude-usage-dial`.

## Deviations / notes
- Step 1: `core.dial_svg` output is byte-identical to the GTK version's (checked at 3 states). Line length is 110
  (the SVG strings), and `parse_usage` is split out of `fetch_usage` for testing. The tray ring now draws the % as text.
- Step 2: An API-key login (no `claudeAiOauth`) now gets its own message, since usage limits only exist for subscriptions.
  `find_claude_code()` also checks the usual install folders, because apps started from a menu or Finder get a short PATH.
  The macOS Keychain path is covered by unit tests only (still **unverified on a real Mac**).
- Step 3: QtSvg renders the dial faithfully, including the glow filter and gradients. Two Qt quirks: it ignores font *lists*
  (FONT is now just "Ubuntu") and it ignores letter-spacing. Ubuntu R/B/L are bundled in `claude_usage/fonts` with the
  Ubuntu Font Licence, so the dial looks the same on Windows/Mac. The rim resize is custom (anchored opposite side,
  stays square). Moving uses `startSystemMove` (works on Wayland), with a manual fallback. Checked live at 360/600 px
  on 2× X11; screenshots need xwininfo + GDK because Qt's grabWindow is unreliable on multi-monitor HiDPI X11. Drag and resize by
  hand **not yet tested**. Settings now live in `~/.config/claude-usage-dial/settings.json`.
- Step 4: Qt's tray talks to the desktop directly over DBus (StatusNotifierItem), so no libappindicator is needed. Checked on
  Ubuntu: a "33" teal ring with the real value and an "80" amber ring when forced, and the tooltip shows both numbers. If there's no
  tray, the dial always shows at startup so the user isn't left with nothing.
- Step 5: The Setup window was checked in both states. ✓ uses the real login and a live "Test now". ✗ uses
  `CLAUDE_CONFIG_DIR` pointed at an empty folder (safer than renaming the real credentials file) plus a stubbed
  `find_claude_code`. Preferences apply immediately. Setup opens on first run and once per distinct fetch error.
  Start-at-login writers are unit-tested for all 3 OSes with a fake winreg; real Windows/Mac **untested**.
  Known cosmetic gap: Qt over-estimates the wrapped-text height, which leaves some empty space above Close.
  Two attempts didn't fix it, so it's left for now. Screenshots now use `QWidget.grab()`, because a screen capture picked up
  another window that was in front.
- Step 6 (in progress): `--self-test` passes from source and from the PyInstaller folder build. The bundle is 131 MB unpacked
  (31 MB of that is Qt's ICU data). It leaves out GTK, its theme plugin and font libraries (AppImage excludelist) and Qt translations.
  The bundled build ran live on Ubuntu with no errors and its tray icon showed. Fixes found on the way: the hatch texture
  spilled past the circle (QtSvg ignores clip-path there; now drawn as a circle), and on first run the dial opened at
  0,0, possibly on a secondary monitor (now centred on the main screen). appimagetool 1.9.1 and runtime 20251108 are pinned by SHA-256.
  The AppImage itself was not built locally; it is built and tested by CI instead (see below).
  The macOS build is Apple silicon only (no Intel Macs) for now.
- Step 7 (docs done, verification pending): the README has been rewritten for end users, plus an MIT LICENSE (holder: "claude-usage-dial
  contributors"), new decisions, and README images rendered offscreen. The GTK `claude_usage.py` and `install.sh` are removed,
  and the old plans are marked superseded. Still to do: follow the README with a real built AppImage (blocked as in step 6).
- Step 6/7 verified 2026-11-21 via CI instead of a local build (the user chose this). Run 44904823380 passed on all three OSes,
  and the self-test passed on each. Download sizes: Linux AppImage 56 MB, Windows exe 35 MB, macOS zip 26 MB. The CI-built
  AppImage (built on 22.04) ran on Ubuntu 24.04: self-test ok; live with a fresh config it showed real data, the tray
  ring, the dial centred on the main screen, Setup on first run, and settings saved. CI fixes: the script was missing its
  exec bit, and the macos-14 runner was retired (now macos-15).
- Step 8 (partial): public repo https://github.com/jonathanw82/claude-usage-dial created and `main` pushed. Commits
  were rewritten first to use the GitHub noreply email (the user's choice), and that email is now set in this repo's git config.
  **Not yet done:** tagging v0.1.0 to publish a Release (needs user OK). Real Windows/Mac hands-on testing is still outstanding.
- Step 8 done 2026-11-21: tagged v0.1.0. The release workflow passed on all three OSes and attached the AppImage (57 MB), the
  Windows exe (35 MB) and the macOS arm64 zip (26 MB): https://github.com/jonathanw82/claude-usage-dial/releases/tag/v0.1.0
  The old GTK install (`~/.local/bin/claude-usage`, its menu and autostart entries, cache and config) has been removed from the dev machine.
- v0.1.1 (2026-11-21, approved by the user): Start/app-menu entry with icon on first run (Windows and Linux), a Setup tick-box,
  re-pointing when the app moves, and single-instance hand-off. Verified on Linux with a CI-built AppImage in ~/Applications:
  the first run created a valid `.desktop` entry (desktop-file-validate passes) and icon; moving the file and relaunching
  updated `Exec` both ways. A second launch re-shows a hidden dial and exits (tested from source). The Windows shortcut is
  covered by unit tests with a fake PowerShell only.
