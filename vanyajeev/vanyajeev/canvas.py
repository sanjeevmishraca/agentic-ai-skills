"""Image canvas: before/after split view, crop with rule-of-thirds, subject box and face point."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QFont, QPainterPath, QBrush
from PySide6.QtWidgets import QWidget

from . import theme

HANDLE = 9


def to_qimage(a: np.ndarray) -> QImage:
    a = np.ascontiguousarray(a)
    h, w = a.shape[:2]
    if a.ndim == 2:
        return QImage(a.data, w, h, w, QImage.Format_Grayscale8).copy()
    return QImage(a.data, w, h, 3 * w, QImage.Format_RGB888).copy()


class Canvas(QWidget):
    cropChanged = Signal(object)      # (x, y, w, h) fractions of full frame, or None
    subjectChanged = Signal(object)   # (x, y, w, h) fractions of cropped frame
    faceChanged = Signal(object)      # (x, y) fractions of cropped frame
    filesDropped = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setMinimumSize(480, 360)
        self.before = self.after = self.mask = None
        self.mode = 'view'
        self.compare = False
        self.split = 0.5
        self.crop = None            # fractions (full frame) while in crop mode
        self.aspect = 1.5           # w/h of the crop, None = free
        self.subject = None
        self.face = None
        self.busy = False
        self._drag = None

    # ------------------------------------------------------------------ data
    def set_images(self, before, after, mask=None):
        self.before = to_qimage(before) if before is not None else None
        self.after = to_qimage(after) if after is not None else None
        if mask is not None:
            m = (np.clip(mask, 0, 1) * 255).astype(np.uint8)
            rgba = np.zeros(m.shape + (4,), np.uint8)
            rgba[..., 0], rgba[..., 1], rgba[..., 2] = 217, 164, 65
            rgba[..., 3] = (m * 0.38).astype(np.uint8)
            h, w = m.shape
            self.mask = QImage(rgba.data, w, h, 4 * w, QImage.Format_RGBA8888).copy()
        else:
            self.mask = None
        self.update()

    def clear(self):
        self.before = self.after = self.mask = None
        self.update()

    def set_mode(self, mode):
        self.mode = mode
        self.setCursor(Qt.CrossCursor if mode in ('crop', 'subject', 'face') else Qt.ArrowCursor)
        self.update()

    # ------------------------------------------------------------------ geometry
    def _img_rect(self):
        img = self.after or self.before
        if img is None:
            return QRectF()
        pad = 24
        W, H = self.width() - 2 * pad, self.height() - 2 * pad
        s = min(W / img.width(), H / img.height())
        w, h = img.width() * s, img.height() * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _to_frac(self, p: QPointF):
        r = self._img_rect()
        return (min(1, max(0, (p.x() - r.x()) / r.width())), min(1, max(0, (p.y() - r.y()) / r.height())))

    def _frac_rect(self, f):
        r = self._img_rect()
        x, y, w, h = f
        return QRectF(r.x() + x * r.width(), r.y() + y * r.height(), w * r.width(), h * r.height())

    # ------------------------------------------------------------------ paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(theme.CANVAS))
        r = self._img_rect()
        if self.after is None:
            self._paint_empty(p)
            return
        if self.compare and self.before is not None and self.mode == 'view':
            sx = r.x() + self.split * r.width()
            p.save(); p.setClipRect(QRectF(r.x(), r.y(), sx - r.x(), r.height())); p.drawImage(r, self.before); p.restore()
            p.save(); p.setClipRect(QRectF(sx, r.y(), r.right() - sx, r.height())); p.drawImage(r, self.after); p.restore()
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
            p.drawLine(QPointF(sx, r.top()), QPointF(sx, r.bottom()))
            p.setBrush(QColor(theme.ACCENT)); p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(sx, r.center().y()), 13, 13)
            p.setPen(QPen(QColor('#1a1612'), 2))
            cy = r.center().y()
            for d in (-1, 1):
                path = QPainterPath(); path.moveTo(sx + d * 3, cy - 5); path.lineTo(sx + d * 8, cy); path.lineTo(sx + d * 3, cy + 5)
                p.drawPath(path)
            self._pill(p, QPointF(r.x() + 14, r.y() + 14), 'Before')
            self._pill(p, QPointF(r.right() - 14, r.y() + 14), 'After', right=True)
        else:
            p.drawImage(r, self.after)
        if self.mode == 'subject' and self.mask is not None:
            p.drawImage(r, self.mask)
        if self.mode == 'crop':
            self._paint_crop(p, r)
        if self.mode == 'subject' and self.subject:
            rr = self._frac_rect(self.subject)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 150), 4)); p.drawRoundedRect(rr, 4, 4)
            p.setPen(QPen(QColor(255, 255, 255, 235), 2, Qt.DashLine)); p.drawRoundedRect(rr, 4, 4)
        if self.mode in ('face', 'subject') and self.face:
            c = QPointF(r.x() + self.face[0] * r.width(), r.y() + self.face[1] * r.height())
            for col, wd in ((QColor(0, 0, 0, 150), 4.5), (QColor(255, 255, 255, 240), 2)):
                p.setPen(QPen(col, wd, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, 18, 18)
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    p.drawLine(QPointF(c.x() + dx * 10, c.y() + dy * 10), QPointF(c.x() + dx * 28, c.y() + dy * 28))
            p.setPen(Qt.NoPen); p.setBrush(QColor(theme.ACCENT)); p.drawEllipse(c, 3.5, 3.5)
        if self.busy:
            self._pill(p, QPointF(self.width() / 2, self.height() - 36), 'Rendering…', center=True)

    def _paint_empty(self, p):
        p.setPen(QPen(QColor(theme.BORDER), 1.5, Qt.DashLine)); p.setBrush(Qt.NoBrush)
        box = QRectF(self.width() / 2 - 230, self.height() / 2 - 120, 460, 240)
        p.drawRoundedRect(box, 18, 18)
        p.setPen(QColor(theme.ACCENT))
        f = QFont(theme.FONT, 30); p.setFont(f)
        p.drawText(QRectF(box.x(), box.y() + 34, box.width(), 50), Qt.AlignCenter, '◐')
        p.setPen(QColor(theme.TEXT)); p.setFont(QFont(theme.FONT, 14, QFont.DemiBold))
        p.drawText(QRectF(box.x(), box.y() + 98, box.width(), 30), Qt.AlignCenter, 'Drop RAW or JPEG photos here')
        p.setPen(QColor(theme.MUTED)); p.setFont(QFont(theme.FONT, 10))
        p.drawText(QRectF(box.x(), box.y() + 132, box.width(), 60), Qt.AlignCenter,
                   'or use Add photos / Add folder above\nCR3 · CR2 · NEF · ARW · RAF · DNG · JPEG · TIFF and more')

    def _pill(self, p, pt, text, right=False, center=False):
        p.setFont(QFont(theme.FONT, 9, QFont.DemiBold))
        w = p.fontMetrics().horizontalAdvance(text) + 20
        x = pt.x() - w if right else (pt.x() - w / 2 if center else pt.x())
        rr = QRectF(x, pt.y(), w, 24)
        p.setPen(Qt.NoPen); p.setBrush(QColor(20, 18, 16, 190)); p.drawRoundedRect(rr, 12, 12)
        p.setPen(QColor(theme.TEXT)); p.drawText(rr, Qt.AlignCenter, text)

    def _paint_crop(self, p, r):
        c = self.crop or (0, 0, 1, 1)
        cr = self._frac_rect(c)
        shade = QPainterPath(); shade.addRect(r); hole = QPainterPath(); hole.addRect(cr)
        p.fillPath(shade.subtracted(hole), QColor(10, 9, 8, 165))
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for i in (1, 2):
            x = cr.x() + cr.width() * i / 3; y = cr.y() + cr.height() * i / 3
            p.drawLine(QPointF(x, cr.top()), QPointF(x, cr.bottom()))
            p.drawLine(QPointF(cr.left(), y), QPointF(cr.right(), y))
        p.setPen(QPen(QColor(theme.ACCENT), 2)); p.setBrush(Qt.NoBrush); p.drawRect(cr)
        p.setBrush(QColor(theme.ACCENT)); p.setPen(Qt.NoPen)
        for pt in (cr.topLeft(), cr.topRight(), cr.bottomLeft(), cr.bottomRight()):
            p.drawRoundedRect(QRectF(pt.x() - HANDLE / 2, pt.y() - HANDLE / 2, HANDLE, HANDLE), 2, 2)

    # ------------------------------------------------------------------ mouse
    def _corner_hit(self, pos):
        if not self.crop:
            return None
        cr = self._frac_rect(self.crop)
        for name, pt in (('tl', cr.topLeft()), ('tr', cr.topRight()), ('bl', cr.bottomLeft()), ('br', cr.bottomRight())):
            if abs(pos.x() - pt.x()) < 12 and abs(pos.y() - pt.y()) < 12:
                return name
        return None

    def mousePressEvent(self, e):
        if self.after is None or e.button() != Qt.LeftButton:
            return
        pos = e.position()
        f = self._to_frac(pos)
        if self.mode == 'view' and self.compare:
            self._drag = ('split',)
            self._set_split(pos)
        elif self.mode == 'crop':
            corner = self._corner_hit(pos)
            if corner:
                self._drag = ('corner', corner)
            elif self.crop and self._frac_rect(self.crop).contains(pos):
                self._drag = ('move', f, self.crop)
            else:
                self._drag = ('new', f)
                self.crop = (f[0], f[1], 0.001, 0.001)
        elif self.mode == 'subject':
            self._drag = ('subject', f)
            self.subject = (f[0], f[1], 0.001, 0.001)
        elif self.mode == 'face':
            self.face = f
            self.faceChanged.emit(self.face)
        self.update()

    def _img_aspect(self):
        img = self.after
        return img.width() / img.height() if img else 1.5

    def _rect_from(self, a, b, aspect):
        x0, y0 = a; x1, y1 = b
        w, h = abs(x1 - x0), abs(y1 - y0)
        if aspect:
            k = aspect / self._img_aspect()           # aspect in fraction units: w_frac = k * h_frac
            if w > k * h:
                h = w / k
            else:
                w = k * h
        x = x0 if x1 >= x0 else x0 - w
        y = y0 if y1 >= y0 else y0 - h
        x, y = max(0, x), max(0, y)
        w, h = min(w, 1 - x), min(h, 1 - y)
        if aspect:
            k = aspect / self._img_aspect()
            if w < k * h:
                h = w / k
            else:
                w = k * h
        return (x, y, w, h)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.mode == 'crop' and not self._drag:
            c = self._corner_hit(pos)
            self.setCursor(Qt.SizeFDiagCursor if c in ('tl', 'br') else Qt.SizeBDiagCursor if c else
                           (Qt.SizeAllCursor if self.crop and self._frac_rect(self.crop).contains(pos) else Qt.CrossCursor))
        if not self._drag:
            return
        f = self._to_frac(pos)
        kind = self._drag[0]
        if kind == 'split':
            self._set_split(pos)
        elif kind == 'new':
            self.crop = self._rect_from(self._drag[1], f, self.aspect)
        elif kind == 'corner':
            x, y, w, h = self.crop
            opp = {'tl': (x + w, y + h), 'tr': (x, y + h), 'bl': (x + w, y), 'br': (x, y)}[self._drag[1]]
            self.crop = self._rect_from(opp, f, self.aspect)
        elif kind == 'move':
            (sx, sy), (x, y, w, h) = self._drag[1], self._drag[2]
            nx = min(max(0, x + f[0] - sx), 1 - w); ny = min(max(0, y + f[1] - sy), 1 - h)
            self.crop = (nx, ny, w, h)
        elif kind == 'subject':
            self.subject = self._rect_from(self._drag[1], f, None)
        self.update()

    def mouseReleaseEvent(self, e):
        if not self._drag:
            return
        kind = self._drag[0]
        self._drag = None
        if kind in ('new', 'corner', 'move'):
            if self.crop and (self.crop[2] < 0.03 or self.crop[3] < 0.03):
                self.crop = None
            self.cropChanged.emit(self.crop)
        elif kind == 'subject':
            if self.subject and (self.subject[2] < 0.02 or self.subject[3] < 0.02):
                self.subject = None
            self.subjectChanged.emit(self.subject)
        self.update()

    def _set_split(self, pos):
        r = self._img_rect()
        self.split = min(1, max(0, (pos.x() - r.x()) / max(1, r.width())))
        self.update()

    # ------------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.filesDropped.emit([u.toLocalFile() for u in e.mimeData().urls()])
