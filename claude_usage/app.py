"""Application wiring: settings, periodic fetching, the dial and the menu."""

import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWidgets import QApplication, QMenu

from . import core, settings
from .credentials import UsageError
from .dial import DialWindow

FONT_DIR = Path(__file__).with_name("fonts")


def load_fonts():
    """Register the bundled Ubuntu fonts so the dial looks the same on every OS."""
    for f in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


class _Bridge(QObject):
    done = Signal(object, object)  # usage, error - emitted from the worker thread


class App(QObject):
    def __init__(self, qapp):
        super().__init__()
        self.qapp = qapp
        self.cfg = settings.load()
        self.usage = None
        self.error = None
        self.updated = None
        self.busy = False
        self.bridge = _Bridge()
        self.bridge.done.connect(self._done)

        self.menu = self._build_menu()
        self.dial = DialWindow(self.menu, self.cfg["size"], (self.cfg["x"], self.cfg["y"])
                               if self.cfg["x"] is not None else None, self.cfg["on_top"])
        self.dial.geometry_changed.connect(self._save_geometry)
        self.dial.refresh_requested.connect(self.refresh)

        self.timer = QTimer(self, timeout=self.refresh)
        self.timer.start(self.cfg["refresh_min"] * 60_000)
        self.tick = QTimer(self, timeout=self.render, interval=30_000)  # countdowns
        self.tick.start()
        if self.cfg["show_dial_at_start"]:
            self.show_dial()
        self.render()
        self.refresh()

    # -- menu --------------------------------------------------------------

    def _build_menu(self):
        menu = QMenu()
        self.act_refresh = QAction("Refresh now", menu, triggered=self.refresh)
        self.act_quit = QAction("Quit", menu, triggered=self.quit)
        menu.addAction(self.act_refresh)
        menu.addSeparator()
        menu.addAction(self.act_quit)
        return menu

    # -- actions -----------------------------------------------------------

    def show_dial(self):
        self.dial.show()
        self.dial.raise_()
        self.dial.activateWindow()

    def quit(self):
        self._save_geometry()
        self.qapp.quit()

    def _save_geometry(self):
        g = self.dial.geometry()
        self.cfg.update(size=g.width(), x=g.x(), y=g.y())
        settings.save(self.cfg)

    # -- data --------------------------------------------------------------

    def refresh(self):
        if self.busy:
            return
        self.busy = True

        def work():
            try:
                usage, error = core.fetch_usage(), None
            except UsageError as e:
                usage, error = None, str(e)
            except Exception as e:  # never let the worker die silently
                usage, error = None, f"Unexpected error: {e}"
            self.bridge.done.emit(usage, error)

        threading.Thread(target=work, daemon=True).start()

    def _done(self, usage, error):
        self.busy = False
        self.error = error
        if usage:
            self.usage = usage
            self.updated = datetime.now()
        self.render()

    def render(self):
        usage = None if self.error else self.usage
        self.dial.update_data(usage, self.error, self.updated,
                              (self.cfg["warn"], self.cfg["crit"]))


def main(argv=None):
    qapp = QApplication(sys.argv if argv is None else argv)
    qapp.setApplicationName(settings.APP_DIR_NAME)
    qapp.setQuitOnLastWindowClosed(False)  # hiding the dial must not quit the app
    load_fonts()
    app = App(qapp)  # noqa: F841 - keep a reference for the event loop's lifetime
    return qapp.exec()
