"""Application wiring: settings, periodic fetching, the dial and the menu."""

import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QByteArray, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFontDatabase, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import core, settings
from .credentials import UsageError
from .dial import DialWindow
from .setup_window import SetupWindow

FONT_DIR = Path(__file__).with_name("fonts")


def load_fonts():
    """Register the bundled Ubuntu fonts so the dial looks the same on every OS."""
    for f in sorted(FONT_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(f))


def svg_pixmap(svg, px):
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p)
    p.end()
    return QPixmap.fromImage(img)


def ring_icon(pct, warn, crit):
    """Tray icon at the sizes trays commonly ask for (sharp on HiDPI too)."""
    icon = QIcon()
    for px in (16, 22, 24, 32, 44, 48, 64):
        icon.addPixmap(svg_pixmap(core.ring_svg(pct, px=px, warn=warn, crit=crit), px))
    return icon


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
        self.setup = None
        self._error_prompted = None  # the error we last opened Setup for (to avoid nagging)
        self.bridge = _Bridge()
        self.bridge.done.connect(self._done)

        self.menu = self._build_menu()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._tray_clicked)
            self.tray.setIcon(ring_icon(None, self.cfg["warn"], self.cfg["crit"]))
            self.tray.show()
        self.dial = DialWindow(self.menu, self.cfg["size"], (self.cfg["x"], self.cfg["y"])
                               if self.cfg["x"] is not None else None, self.cfg["on_top"])
        self.dial.geometry_changed.connect(self._save_geometry)
        self.dial.refresh_requested.connect(self.refresh)

        self.timer = QTimer(self, timeout=self.refresh)
        self.timer.start(self.cfg["refresh_min"] * 60_000)
        self.tick = QTimer(self, timeout=self.render, interval=30_000)  # countdowns
        self.tick.start()
        self.act_on_top.setChecked(self.cfg["on_top"])
        # With no tray (some Linux desktops), the dial is the only way in, so always show it.
        if self.cfg["show_dial_at_start"] or self.tray is None:
            self.show_dial()
        self.render()
        self.refresh()
        if not self.cfg["setup_seen"]:  # first run: guide the user
            self.open_setup()

    # -- menu --------------------------------------------------------------

    def _build_menu(self):
        menu = QMenu()
        self.act_session = QAction("Session: …", menu, enabled=False)
        self.act_week = QAction("Week: …", menu, enabled=False)
        self.act_status = QAction("Loading…", menu, enabled=False)
        self.act_show = QAction("Show dial", menu, triggered=self.toggle_dial)
        self.act_setup = QAction("Setup…", menu, triggered=self.open_setup)
        self.act_on_top = QAction("Always on top", menu, checkable=True,
                                  toggled=self.set_on_top)
        self.act_refresh = QAction("Refresh now", menu, triggered=self.refresh)
        self.act_quit = QAction("Quit", menu, triggered=self.quit)
        for a in (self.act_session, self.act_week, self.act_status):
            menu.addAction(a)
        menu.addSeparator()
        for a in (self.act_show, self.act_setup, self.act_on_top, self.act_refresh):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(self.act_quit)
        menu.aboutToShow.connect(  # the dial can be hidden with Esc/double-click meanwhile
            lambda: self.act_show.setText("Hide dial" if self.dial.isVisible() else "Show dial"))
        return menu

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # left click (where the desktop reports it)
            self.toggle_dial()

    # -- actions -----------------------------------------------------------

    def toggle_dial(self):
        if self.dial.isVisible():
            self.dial.hide()
        else:
            self.show_dial()

    def set_on_top(self, on):
        self.cfg["on_top"] = on
        self.dial.set_on_top(on)
        settings.save(self.cfg)

    def open_setup(self):
        if self.setup is None:
            self.setup = SetupWindow(self.cfg)
            self.setup.prefs_changed.connect(self.apply_prefs)
        self.setup.show()
        self.setup.raise_()
        self.setup.activateWindow()
        if not self.cfg["setup_seen"]:
            self.cfg["setup_seen"] = True
            settings.save(self.cfg)

    def apply_prefs(self, prefs):
        old_refresh = self.cfg["refresh_min"]
        self.cfg.update(prefs)
        settings.save(self.cfg)
        if self.act_on_top.isChecked() != self.cfg["on_top"]:
            self.act_on_top.setChecked(self.cfg["on_top"])  # also updates the dial
        if self.cfg["refresh_min"] != old_refresh:
            self.timer.start(self.cfg["refresh_min"] * 60_000)
        self.render()

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
            self._error_prompted = None
        elif error and error != self._error_prompted:
            # Something is wrong (e.g. signed out): open Setup once per distinct problem.
            self._error_prompted = error
            self.open_setup()
            self.setup.check()
        self.render()

    def render(self):
        usage = None if self.error else self.usage
        warn, crit = self.cfg["warn"], self.cfg["crit"]
        self.dial.update_data(usage, self.error, self.updated, (warn, crit))
        s_pct, s_reset = usage["session"] if usage else (None, None)
        w_pct, w_reset = usage["week"] if usage else (None, None)
        self.act_session.setText(f"Session: {core.fmt_pct(s_pct)} — {core.fmt_reset(s_reset)}")
        self.act_week.setText(f"Week: {core.fmt_pct(w_pct)} — {core.fmt_reset(w_reset)}")
        self.act_status.setText(self.error or (
            f"Updated {self.updated:%H:%M:%S}" if self.updated else "Loading…"))
        self.act_show.setText("Hide dial" if self.dial.isVisible() else "Show dial")
        if self.tray:
            self.tray.setIcon(ring_icon(s_pct, warn, crit))
            self.tray.setToolTip(f"Claude usage\nSession {core.fmt_pct(s_pct)} · "
                                 f"Week {core.fmt_pct(w_pct)}"
                                 + (f"\n{self.error}" if self.error else ""))


def self_test():
    """Check a build works without a screen or network: fonts, dial and tray icon render.
    Used by CI on every OS. Returns a process exit code."""
    from datetime import timedelta, timezone

    from PySide6.QtGui import QFontInfo

    from .setup_window import SetupWindow
    now = datetime.now(timezone.utc)
    usage = {"session": (42.0, now + timedelta(hours=2)), "week": (64.0, now + timedelta(days=3))}
    checks = {}
    families = set(QFontDatabase.families())
    checks["bundled font"] = "Ubuntu" in families
    img = svg_pixmap(core.dial_svg(usage, updated=datetime.now(), px=200), 200).toImage()
    checks["dial renders"] = img.pixelColor(100, 100).alpha() == 255 and \
        img.pixelColor(1, 1).alpha() == 0  # opaque face, transparent corner
    checks["tray icon renders"] = not ring_icon(42.0, 75, 90).isNull()
    checks["setup window builds"] = SetupWindow(settings.load()) is not None
    checks["font resolves"] = QFontInfo(QApplication.font()).family() != ""
    for name, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


def main(argv=None):
    argv = sys.argv if argv is None else argv
    if "--self-test" in argv:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    qapp = QApplication(argv)
    qapp.setApplicationName(settings.APP_DIR_NAME)
    qapp.setQuitOnLastWindowClosed(False)  # hiding the dial must not quit the app
    load_fonts()
    if "--self-test" in argv:
        return self_test()
    app = App(qapp)  # noqa: F841 - keep a reference for the event loop's lifetime
    return qapp.exec()
