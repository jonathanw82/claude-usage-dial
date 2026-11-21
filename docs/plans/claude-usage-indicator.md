# Plan: Claude usage indicator (Ubuntu top bar + window)

> **Superseded (2026-11-21):** the GTK app this plan describes has been replaced by the Qt version — see `portable-release.md`.

Goal: show Claude current-session (5h) % and this-week (7d) % on the Ubuntu 24.04 GNOME desktop.
Chosen style: **both** — top-bar indicator, plus a window with progress bars opened from its menu.

## Steps

- [x] Write `claude_usage.py` (GTK3 + AyatanaAppIndicator3, stdlib only)
  - Verify: `python3 -m py_compile claude_usage.py` ✅ — formatting helpers tested offline ✅
- [x] Write `install.sh` (copies to `~/.local/bin/claude-usage`, app-menu + autostart `.desktop`)
  - Verify: `bash -n install.sh` ✅
- [x] Write `README.md` (setup, how it works, uninstall)
- [x] **User:** install dependency `sudo apt install gir1.2-ayatanaappindicator3-0.1`
  - Verify: `python3 -c "import gi; gi.require_version('AyatanaAppIndicator3','0.1')"` exits 0
- [ ] Run `./install.sh`; label `S x% · W y%` appears in the top bar
  - Verify: numbers match `/usage` in Claude Code
- [x] Confirm the usage endpoint's response shape matches the parser (`five_hour` / `seven_day`,
      each with `utilization` (0–100) and `resets_at` (ISO 8601)) — ✅ verified 2026-11-21
  - Verify: if numbers are wrong/blank, capture the window's error text or the raw JSON and fix `fetch_usage()`
- [ ] Open "Show window" from the menu; bars and countdowns render, colours change at 75 % / 90 %
- [ ] Error state: temporarily rename `~/.claude/.credentials.json` → indicator shows `S –% · W –%`
      and the reason; restore the file → recovers on "Refresh now"
- [ ] Log out/in → indicator autostarts

## Deviations / notes

- 2026-11-20: The live endpoint test was deferred to the first real run.
- `AppIndicator3` (old namespace) isn't installed; only the Ayatana library is, minus its GI bindings
  — hence the apt package above.
- Folder is not a git repo, so there are no commits yet.
- 2026-11-21: Dependency installed; endpoint shape confirmed. `install.sh` ran, but the app it launched
  died at once when launched from a VS Code snap terminal, whose env (GTK_PATH, LOCPATH, …)
  pulls in /snap/core20 libs → `undefined symbol: __libc_pthread_init`. Launching with a clean env
  works. Normal menu/autostart launches aren't affected; launching from a VS Code terminal is.
