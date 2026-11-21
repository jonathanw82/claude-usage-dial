"""The round, borderless dial window (Qt)."""

import math

from PySide6.QtCore import QByteArray, QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QRegion
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from . import core
from .settings import LIMITS

RIM = 0.88  # pointer further out than this fraction of the radius = resize, not move
_CURSORS = [Qt.SizeVerCursor, Qt.SizeBDiagCursor, Qt.SizeHorCursor, Qt.SizeFDiagCursor] * 2


class DialWindow(QWidget):
    """Drag the face to move, drag the rim to resize (stays round), double-click or Esc to hide,
    right-click for the menu, R/F5 to refresh. Emits `geometry_changed` when moved or resized."""

    geometry_changed = Signal()
    refresh_requested = Signal()

    def __init__(self, menu, size, pos=None, on_top=True):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool)
        self.menu = menu
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Claude usage")
        self.setMouseTracking(True)
        self.set_on_top(on_top)
        self.data = (None, None, None)  # usage, error, updated
        self.thresholds = (core.WARN_PCT, core.CRIT_PCT)
        self._image = None
        self._drag = None  # (anchor QPoint, edge index) during a rim resize
        self._render_timer = QTimer(self, singleShot=True, interval=150, timeout=self._render)
        self._save_timer = QTimer(self, singleShot=True, interval=500,
                                  timeout=self.geometry_changed.emit)
        self.resize(size, size)
        if pos and self._on_a_screen(pos, size):
            self.move(*pos)
        else:  # first run (or its monitor is gone): centre on the main screen
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                self.move(screen.availableGeometry().center() - QPoint(size // 2, size // 2))
        self._render()

    # -- state -------------------------------------------------------------

    def set_on_top(self, on):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, on)
        if visible:  # changing flags hides the window
            self.show()

    def update_data(self, usage, error, updated, thresholds):
        self.data = (usage, error, updated)
        self.thresholds = thresholds
        self._render()
        when = f"Updated {updated:%H:%M:%S}" if updated else "Loading…"
        self.setToolTip(error or when)

    @staticmethod
    def _on_a_screen(pos, size):
        centre = QPoint(pos[0] + size // 2, pos[1] + size // 2)
        return QGuiApplication.screenAt(centre) is not None

    # -- drawing -------------------------------------------------------------

    def _render(self):
        """Rasterise the SVG at real device pixels, so it is sharp at any size and DPI."""
        usage, error, updated = self.data
        dpr = self.devicePixelRatioF()
        px = max(1, round(self.width() * dpr))
        warn, crit = self.thresholds
        svg = core.dial_svg(usage, error, updated, px=px, warn=warn, crit=crit)
        img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(p)
        p.end()
        img.setDevicePixelRatio(dpr)
        self._image = img
        self.update()

    def paintEvent(self, _ev):
        if self._image is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.drawImage(self.rect(), self._image)  # stretched while a resize is in progress

    def resizeEvent(self, ev):
        # Clicks only count inside the circle: the corners pass through to what's behind.
        self.setMask(QRegion(self.rect(), QRegion.Ellipse))
        self._render_timer.start()
        self._save_timer.start()
        super().resizeEvent(ev)

    def moveEvent(self, ev):
        self._save_timer.start()
        super().moveEvent(ev)

    # -- mouse and keys ------------------------------------------------------

    def _rim_edge(self, pos):
        """Index 0-7 (N, NE, E, SE, S, SW, W, NW) if pos is on the rim, else None."""
        r = self.width() / 2
        dx, dy = pos.x() - r, pos.y() - r
        if math.hypot(dx, dy) < r * RIM:
            return None
        angle = math.degrees(math.atan2(dx, -dy)) % 360
        return int((angle + 22.5) // 45) % 8

    def mousePressEvent(self, ev):
        if ev.button() == Qt.RightButton:
            self.menu.popup(ev.globalPosition().toPoint())
        elif ev.button() == Qt.LeftButton:
            edge = self._rim_edge(ev.position())
            if edge is not None:
                # Resize ourselves, keeping the opposite side fixed and the dial square.
                g = self.geometry()
                ax = g.left() if edge in (1, 2, 3) else g.right() if edge in (5, 6, 7) else g.center().x()
                ay = g.top() if edge in (3, 4, 5) else g.bottom() if edge in (7, 0, 1) else g.center().y()
                self._drag = (QPoint(ax, ay), edge)
            elif not self.windowHandle().startSystemMove():
                self._drag = ("move", ev.globalPosition().toPoint() - self.pos())

    def mouseMoveEvent(self, ev):
        if self._drag is None:
            edge = self._rim_edge(ev.position())
            self.setCursor(_CURSORS[edge] if edge is not None else Qt.ArrowCursor)
            return
        gp = ev.globalPosition().toPoint()
        if self._drag[0] == "move":
            self.move(gp - self._drag[1])
            return
        anchor, edge = self._drag
        dx, dy = gp.x() - anchor.x(), gp.y() - anchor.y()
        if edge in (0, 4):
            size = abs(dy)
        elif edge in (2, 6):
            size = abs(dx)
        else:
            size = max(abs(dx), abs(dy))
        lo, hi = LIMITS["size"]
        size = int(min(hi, max(lo, size)))
        x = anchor.x() if edge in (1, 2, 3) else anchor.x() - size if edge in (5, 6, 7) \
            else anchor.x() - size // 2
        y = anchor.y() if edge in (3, 4, 5) else anchor.y() - size if edge in (7, 0, 1) \
            else anchor.y() - size // 2
        self.setGeometry(QRect(x, y, size, size))

    def mouseReleaseEvent(self, _ev):
        self._drag = None

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.hide()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.hide()
        elif ev.key() in (Qt.Key_R, Qt.Key_F5):
            self.refresh_requested.emit()
        else:
            super().keyPressEvent(ev)
