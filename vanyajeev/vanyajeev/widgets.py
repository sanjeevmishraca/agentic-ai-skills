"""Small custom widgets."""
from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, Property, QEasingCurve, QSize
from PySide6.QtGui import QPainter, QColor, QFont
from PySide6.QtWidgets import QCheckBox

from . import theme


class Toggle(QCheckBox):
    """iOS/Fluent-style switch with an animated knob."""

    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 0.0
        self._anim = QPropertyAnimation(self, b'knob', self, duration=140, easingCurve=QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, on):
        self._anim.stop(); self._anim.setStartValue(self._pos); self._anim.setEndValue(1.0 if on else 0.0); self._anim.start()

    def setChecked(self, v):
        super().setChecked(v)
        self._pos = 1.0 if v else 0.0
        self.update()

    def get_knob(self):
        return self._pos

    def set_knob(self, v):
        self._pos = v; self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(44 + 10 + fm.horizontalAdvance(self.text()), max(24, fm.height() + 6))

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        h = 22; y = (self.height() - h) / 2
        track = QRectF(0, y, 40, h)
        on = QColor(theme.ACCENT); off = QColor(theme.BORDER)
        t = self._pos
        col = QColor(int(off.red() + (on.red() - off.red()) * t), int(off.green() + (on.green() - off.green()) * t),
                     int(off.blue() + (on.blue() - off.blue()) * t))
        if not self.isEnabled():
            col.setAlpha(110)
        p.setPen(Qt.NoPen); p.setBrush(col); p.drawRoundedRect(track, h / 2, h / 2)
        p.setBrush(QColor('#fbf7f0') if self.isEnabled() else QColor('#8a837b'))
        p.drawEllipse(QRectF(3 + t * 18, y + 3, h - 6, h - 6))
        p.setPen(QColor(theme.TEXT) if self.isEnabled() else QColor('#6b635b'))
        p.drawText(QRectF(50, 0, self.width() - 50, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text())
