# Claude Usage indicator

Shows your Claude **current session (5-hour)** and **this week (7-day)** usage % in the
Ubuntu top bar, e.g. `S 42% · W 17%`.

- **Top bar:** a small ring that fills with your session %, next to the `S x% · W y%` label.
- **Click** it to open a menu with reset times, *Show window*, *Refresh now* and *Quit*.
- **Show window**: a round, smartwatch-style dial floating on the desktop. The big number is
  the session %. The arcs, small ring and bottom bar show the week %, and the highlighted weekday
  is when the weekly limit resets. Everything is teal, turning amber at ≥ 75 % and red at ≥ 90 %.
  - **Drag** the face to move it, and drag the **outer rim** to resize it (it stays round; 180–1200 px).
    **Double-click** or press **Esc** to hide it. **Right-click** opens the menu, and **R** refreshes.
  - Its size and position are remembered (`~/.config/claude-usage/window.json`). It stays on top of
    other windows by default; untick **Always on top** in the menu to turn that off.
- Refreshes every 5 minutes.

## How it works

It reads the Claude Code login token from `~/.claude/.credentials.json` and calls
`https://api.anthropic.com/api/oauth/usage`. The token is sent only to Anthropic, and the
credentials file is never modified. If the token has expired, run any `claude` command
to refresh it; the indicator picks it up on the next refresh.

## Install

```bash
sudo apt install gir1.2-ayatanaappindicator3-0.1   # one-time dependency
./install.sh
```

This copies the script to `~/.local/bin/claude-usage`, adds a "Claude Usage" app-menu
entry, and starts it at login. Re-run `./install.sh` after editing `claude_usage.py`.

Run without installing: `python3 claude_usage.py`

> Don't launch it from a VS Code (snap) terminal. The snap's environment makes GTK apps crash
> (`undefined symbol: __libc_pthread_init`). Use a normal terminal or the app menu.

## Uninstall

```bash
pkill -f ~/.local/bin/claude-usage
rm ~/.local/bin/claude-usage \
   ~/.local/share/applications/claude-usage.desktop \
   ~/.config/autostart/claude-usage.desktop
rm -r ~/.cache/claude-usage ~/.config/claude-usage
```
