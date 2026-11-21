"""The Setup window: requirements check, connection test, preferences and privacy notice."""

import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import __version__, autostart, core, credentials, launcher
from .credentials import UsageError

OK, BAD = "#2e9e6b", "#d9534f"
CLAUDE_CODE_URL = "https://claude.com/claude-code"

PRIVACY = (
    "This app reads the login that <b>Claude Code</b> saved on this computer and uses it only "
    "to ask Anthropic for your usage numbers. The login is sent only to "
    "<code>api.anthropic.com</code>; it is never stored elsewhere, changed, or sent anywhere "
    "else. The usage service it calls is not officially documented, so a future change by "
    "Anthropic could stop it working until the app is updated. This app is not made by or "
    "affiliated with Anthropic."
)


class _Bridge(QObject):
    tested = Signal(object, object)  # usage, error


def _status_row(title):
    mark, head, detail = QLabel(), QLabel(f"<b>{title}</b>"), QLabel()
    mark.setFixedWidth(22)
    mark.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
    detail.setWordWrap(True)
    detail.setTextInteractionFlags(Qt.TextBrowserInteraction)
    detail.setOpenExternalLinks(True)
    text = QVBoxLayout()
    text.setSpacing(2)
    text.addWidget(head)
    text.addWidget(detail)
    row = QHBoxLayout()
    row.addWidget(mark)
    row.addLayout(text, 1)
    return row, mark, detail


def _set_mark(label, ok):
    label.setText(f'<span style="color:{OK if ok else BAD}; font-size:16px">'
                  f'{"✓" if ok else "✗"}</span>')


class SetupWindow(QWidget):
    """Preferences are applied as soon as they change; `prefs_changed` tells the app."""

    prefs_changed = Signal(dict)

    def __init__(self, cfg):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Claude Usage Dial — Setup")
        self.setFixedWidth(560)  # fixed width so wrapped text gets its full height
        self.cfg = cfg
        self.bridge = _Bridge()
        self.bridge.tested.connect(self._tested)
        root = QVBoxLayout(self)

        # 1. requirements
        req = QGroupBox("1. Requirements")
        lay = QVBoxLayout(req)
        row, self.cc_mark, self.cc_detail = _status_row("Claude Code installed")
        lay.addLayout(row)
        row, self.login_mark, self.login_detail = _status_row("Signed in to Claude Code")
        lay.addLayout(row)
        recheck = QPushButton("Re-check", clicked=lambda: (self.check(), self._fit()))
        lay.addWidget(recheck, 0, Qt.AlignRight)
        root.addWidget(req)

        # 2. connection
        conn = QGroupBox("2. Test connection")
        lay = QHBoxLayout(conn)
        self.test_btn = QPushButton("Test now", clicked=self.test_connection)
        self.test_result = QLabel("Fetch your usage once to check everything works.")
        self.test_result.setWordWrap(True)
        lay.addWidget(self.test_btn)
        lay.addWidget(self.test_result, 1)
        root.addWidget(conn)

        # 3. preferences
        prefs = QGroupBox("3. Preferences")
        form = QFormLayout(prefs)
        self.start_login = QCheckBox("Start when I log in")
        self.in_menu = QCheckBox(launcher.label())
        self.in_menu.setVisible(launcher.supported())  # macOS: Applications/Launchpad already
        self.on_top = QCheckBox("Keep the dial on top of other windows")
        self.show_start = QCheckBox("Show the dial when the app starts")
        self.refresh = self._spin(1, 60, " min")
        self.warn = self._spin(1, 99, " %")
        self.crit = self._spin(2, 100, " %")
        form.addRow(self.start_login)
        form.addRow(self.in_menu)
        form.addRow(self.on_top)
        form.addRow(self.show_start)
        form.addRow("Refresh every", self.refresh)
        form.addRow("Amber warning from", self.warn)
        form.addRow("Red warning from", self.crit)
        self.autostart_error = QLabel()
        self.autostart_error.setStyleSheet(f"color:{BAD}")
        self.autostart_error.hide()
        form.addRow(self.autostart_error)
        root.addWidget(prefs)

        # 4. privacy
        priv = QGroupBox("4. Privacy")
        lay = QVBoxLayout(priv)
        note = QLabel(PRIVACY)
        note.setWordWrap(True)
        lay.addWidget(note)
        root.addWidget(priv)

        for box in (req, conn, prefs, priv):  # boxes hug their content
            box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        root.addStretch(1)
        bottom = QHBoxLayout()
        bottom.addWidget(QLabel(f'<span style="color:gray">Version {__version__}</span>'))
        bottom.addStretch(1)
        bottom.addWidget(QPushButton("Close", clicked=self.close, default=True))
        root.addLayout(bottom)

        self.load_prefs()
        for w in (self.on_top, self.show_start):
            w.toggled.connect(self._prefs_edited)
        for w in (self.refresh, self.warn, self.crit):
            w.valueChanged.connect(self._prefs_edited)
        self.start_login.toggled.connect(self._autostart_toggled)
        self.in_menu.toggled.connect(self._menu_toggled)
        self.check()
        self._fit()

    @staticmethod
    def _spin(lo, hi, suffix):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSuffix(suffix)
        return s

    # -- requirements --------------------------------------------------------

    def check(self):
        path = credentials.find_claude_code()
        _set_mark(self.cc_mark, bool(path))
        self.cc_detail.setText(
            f"Found at <code>{path}</code>" if path else
            f'Not found. Install it from <a href="{CLAUDE_CODE_URL}">{CLAUDE_CODE_URL}</a>, '
            "then press Re-check. (If you installed it somewhere unusual this can be wrong "
            "- what matters is the sign-in check below.)")
        ok, msg = credentials.login_status()
        _set_mark(self.login_mark, ok)
        self.login_detail.setText(msg if ok else (
            f"{msg}.<br>Fix: open a terminal, run <code>claude</code> and sign in with your "
            "Claude account (type <code>/login</code> if it doesn't ask). Then press Re-check."))
        return ok

    # -- connection ------------------------------------------------------------

    def test_connection(self):
        self.test_btn.setEnabled(False)
        self.test_result.setText("Testing…")

        def work():
            try:
                usage, error = core.fetch_usage(), None
            except UsageError as e:
                usage, error = None, str(e)
            except Exception as e:  # shown to the user rather than crashing the window
                usage, error = None, f"Unexpected error: {e}"
            self.bridge.tested.emit(usage, error)

        threading.Thread(target=work, daemon=True).start()

    def _tested(self, usage, error):
        self.test_btn.setEnabled(True)
        self._fit()
        if error:
            self.test_result.setText(f'<span style="color:{BAD}">✗ {error}</span>')
        else:
            self.test_result.setText(
                f'<span style="color:{OK}">✓ Working</span> — session '
                f'{core.fmt_pct(usage["session"][0])}, week {core.fmt_pct(usage["week"][0])}')

    # -- preferences -----------------------------------------------------------

    def load_prefs(self):
        widgets = (self.start_login, self.in_menu, self.on_top, self.show_start, self.refresh, self.warn,
                   self.crit)
        for w in widgets:
            w.blockSignals(True)
        self.start_login.setChecked(autostart.is_enabled())
        self.in_menu.setChecked(launcher.is_installed())
        self.on_top.setChecked(self.cfg["on_top"])
        self.show_start.setChecked(self.cfg["show_dial_at_start"])
        self.refresh.setValue(self.cfg["refresh_min"])
        self.warn.setValue(self.cfg["warn"])
        self.crit.setValue(self.cfg["crit"])
        for w in widgets:
            w.blockSignals(False)

    def _prefs_edited(self):
        warn, crit = self.warn.value(), self.crit.value()
        if warn >= crit:  # keep amber below red
            if self.sender() is self.warn:
                self.crit.setValue(min(100, warn + 1))
            else:
                self.warn.setValue(max(1, crit - 1))
            return  # the corrected spin box will call us again
        self.prefs_changed.emit({
            "on_top": self.on_top.isChecked(),
            "show_dial_at_start": self.show_start.isChecked(),
            "refresh_min": self.refresh.value(), "warn": warn, "crit": crit,
        })

    def _autostart_toggled(self, on):
        try:
            autostart.set_enabled(on)
            self.autostart_error.hide()
        except OSError as e:
            self.autostart_error.setText(f"Couldn't change start-at-login: {e}")
            self.autostart_error.show()
            self.start_login.blockSignals(True)
            self.start_login.setChecked(autostart.is_enabled())
            self.start_login.blockSignals(False)

    def _fit(self):
        self.layout().activate()
        self.adjustSize()

    def _menu_toggled(self, on):
        try:
            launcher.install() if on else launcher.remove()
            self.autostart_error.hide()
        except OSError as e:
            self.autostart_error.setText(str(e))
            self.autostart_error.show()
            self.in_menu.blockSignals(True)
            self.in_menu.setChecked(launcher.is_installed())
            self.in_menu.blockSignals(False)

    def showEvent(self, ev):
        self.load_prefs()  # e.g. "Always on top" may have been changed from the menu
        super().showEvent(ev)
