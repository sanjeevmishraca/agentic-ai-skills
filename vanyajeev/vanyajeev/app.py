"""Vanyajeev — wildlife RAW & JPEG developer for Windows."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QRunnable, QThreadPool, QTimer, Signal, QSize, QSettings, QUrl
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QHBoxLayout,
                               QVBoxLayout, QListWidget, QListWidgetItem, QSlider, QCheckBox, QComboBox, QLineEdit,
                               QScrollArea, QFileDialog, QStatusBar, QProgressBar, QButtonGroup, QMessageBox, QSizePolicy)

from . import engine as E
from . import theme
from .canvas import Canvas, to_qimage
from .widgets import Toggle

APP = 'Vanyajeev'
VERSION = '1.0.0'
ASSETS = Path(__file__).resolve().parent / 'assets'
ASPECTS = [('Original (3:2)', 1.5), ('16:9 wide', 16 / 9), ('2:1 panorama', 2.0), ('4:5 portrait', 0.8),
           ('1:1 square', 1.0), ('Free', None)]
PRINT = [('Off', 0), ('2× print master', 2), ('3× (largest)', 3)]


# ----------------------------------------------------------------------------- workers
class _Sig(QObject):
    done = Signal(object)
    fail = Signal(str)
    progress = Signal(str, float)


class Job(QRunnable):
    def __init__(self, fn, *a, **k):
        super().__init__()
        self.fn, self.a, self.k, self.s = fn, a, k, _Sig()

    def run(self):
        try:
            r = self.fn(*self.a, **self.k)
        except Exception as e:  # surface to the UI
            traceback.print_exc()
            try:
                self.s.fail.emit(str(e))
            except RuntimeError:     # window already closed
                pass
            return
        try:
            self.s.done.emit(r)
        except RuntimeError:
            pass


# ----------------------------------------------------------------------------- helpers
def section(text):
    l = QLabel(text.upper()); l.setObjectName('section'); return l


def hint(text):
    l = QLabel(text); l.setObjectName('hint'); l.setWordWrap(True); return l


def hbox(*ws, spacing=8, stretch_at=None):
    w = QWidget(); lay = QHBoxLayout(w); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(spacing)
    for i, x in enumerate(ws):
        if x == 'stretch':
            lay.addStretch(1)
        else:
            lay.addWidget(x)
    return w


# ----------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP)
        self.setWindowIcon(QIcon(str(ASSETS / 'icon.png')))
        self.resize(1480, 920)
        self.setMinimumSize(1100, 700)
        self.settings = QSettings(APP, APP)
        self.pool = QThreadPool.globalInstance()
        self.photos: list[E.Photo] = []
        self.current: E.Photo | None = None
        self.gen = 0
        self.mask_cache = {}
        self.exporting = False
        self.jobs = set()                    # keep running jobs (and their signal objects) alive
        self.render_timer = QTimer(self, singleShot=True, interval=140, timeout=self._render)

        root = QWidget(objectName='root'); self.setCentralWidget(root)
        v = QVBoxLayout(root); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        v.addWidget(self._header())
        body = QHBoxLayout(); body.setContentsMargins(0, 0, 0, 0); body.setSpacing(0)
        body.addWidget(self._sidebar())
        center = QVBoxLayout(); center.setContentsMargins(0, 0, 0, 0); center.setSpacing(0)
        center.addWidget(self._toolbar())
        self.canvas = Canvas()
        self.canvas.cropChanged.connect(self._on_crop)
        self.canvas.subjectChanged.connect(self._on_subject)
        self.canvas.faceChanged.connect(self._on_face)
        self.canvas.filesDropped.connect(self.add_paths)
        center.addWidget(self.canvas, 1)
        cw = QWidget(); cw.setLayout(center)
        body.addWidget(cw, 1)
        body.addWidget(self._inspector())
        bw = QWidget(); bw.setLayout(body)
        v.addWidget(bw, 1)

        sb = QStatusBar(); self.setStatusBar(sb)
        self.status = QLabel('Ready'); self.status.setObjectName('muted')
        self.prog = QProgressBar(); self.prog.setFixedWidth(220); self.prog.setTextVisible(False); self.prog.hide()
        self.open_btn = QPushButton('Open output folder', objectName='ghost', clicked=self._open_output); self.open_btn.hide()
        sb.addWidget(self.status, 1); sb.addPermanentWidget(self.open_btn); sb.addPermanentWidget(self.prog)

        self.setAcceptDrops(True)
        for key, slot in (('Ctrl+O', self.add_files), ('Ctrl+E', self.export_selected), ('C', lambda: self._mode_btn('crop')),
                          ('S', lambda: self._mode_btn('subject')), ('F', lambda: self._mode_btn('face')),
                          ('V', lambda: self._mode_btn('view')), ('B', lambda: self.compare.toggle())):
            a = QAction(self); a.setShortcut(QKeySequence(key)); a.triggered.connect(slot); self.addAction(a)
        self._sync_controls()

    def _start(self, job):
        job.setAutoDelete(False)
        self.jobs.add(job)
        job.s.done.connect(lambda *_: self.jobs.discard(job))
        job.s.fail.connect(lambda *_: self.jobs.discard(job))
        self.pool.start(job)

    # ------------------------------------------------------------------ layout pieces
    def _header(self):
        f = QFrame(objectName='header'); f.setFixedHeight(64)
        lay = QHBoxLayout(f); lay.setContentsMargins(20, 0, 16, 0); lay.setSpacing(10)
        logo = QLabel(); logo.setPixmap(QPixmap(str(ASSETS / 'icon.png')).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(logo)
        lay.addWidget(QLabel(APP, objectName='wordmark'))
        lay.addWidget(QLabel('वन्यजीव', objectName='devanagari'))
        lay.addSpacing(18)
        lay.addWidget(QPushButton('Add photos', clicked=self.add_files))
        lay.addWidget(QPushButton('Add folder', clicked=self.add_folder))
        lay.addStretch(1)
        self.export_sel = QPushButton('Export selected', clicked=self.export_selected)
        self.export_all = QPushButton('Export all', objectName='primary', clicked=self.export_everything)
        lay.addWidget(self.export_sel); lay.addWidget(self.export_all)
        return f

    def _sidebar(self):
        f = QFrame(objectName='sidebar'); f.setFixedWidth(232)
        lay = QVBoxLayout(f); lay.setContentsMargins(12, 14, 12, 12); lay.setSpacing(8)
        top = QHBoxLayout(); top.addWidget(section('Photos')); top.addStretch(1)
        self.count = QLabel('0', objectName='muted'); top.addWidget(self.count)
        lay.addLayout(top)
        self.list = QListWidget()
        self.list.setViewMode(QListWidget.IconMode); self.list.setFlow(QListWidget.LeftToRight); self.list.setWrapping(True)
        self.list.setResizeMode(QListWidget.Adjust); self.list.setMovement(QListWidget.Static)
        self.list.setIconSize(QSize(176, 118)); self.list.setGridSize(QSize(196, 150)); self.list.setSpacing(2)
        self.list.setSelectionMode(QListWidget.ExtendedSelection); self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._select)
        lay.addWidget(self.list, 1)
        self.remove_btn = QPushButton('Remove from list', objectName='ghost', clicked=self._remove)
        lay.addWidget(self.remove_btn)
        return f

    def _toolbar(self):
        f = QFrame(objectName='toolbar'); f.setFixedHeight(52)
        lay = QHBoxLayout(f); lay.setContentsMargins(16, 8, 16, 8)
        box = QFrame(objectName='segbox'); bl = QHBoxLayout(box); bl.setContentsMargins(3, 3, 3, 3); bl.setSpacing(2)
        self.modes = QButtonGroup(self); self.mode_btns = {}
        for key, label, tip in (('view', 'View', 'V'), ('crop', 'Crop', 'C — drag on the full frame; thirds grid shown'),
                                ('subject', 'Subject', 'S — drag a box around the animal'), ('face', 'Face', 'F — click the eyes')):
            b = QPushButton(label, objectName='seg', checkable=True); b.setToolTip(tip)
            b.clicked.connect(lambda _=False, k=key: self._set_mode(k))
            self.modes.addButton(b); bl.addWidget(b); self.mode_btns[key] = b
        self.mode_btns['view'].setChecked(True)
        lay.addWidget(box)
        lay.addSpacing(12)
        self.compare = QPushButton('Before / After', objectName='seg', checkable=True, toggled=self._toggle_compare)
        self.compare.setToolTip('B — drag the divider to compare')
        cb = QFrame(objectName='segbox'); cl = QHBoxLayout(cb); cl.setContentsMargins(3, 3, 3, 3); cl.addWidget(self.compare)
        lay.addWidget(cb)
        lay.addStretch(1)
        self.mode_hint = QLabel('', objectName='muted'); lay.addWidget(self.mode_hint)
        return f

    def _inspector(self):
        f = QFrame(objectName='inspector'); f.setFixedWidth(330)
        outer = QVBoxLayout(f); outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); outer.addWidget(sc)
        w = QWidget(objectName='inspectorBody'); sc.setWidget(w)
        lay = QVBoxLayout(w); lay.setContentsMargins(18, 8, 18, 18); lay.setSpacing(9)

        self.title = QLabel('No photo selected'); self.title.setStyleSheet('font-size: 11pt; font-weight: 600;')
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        lay.addWidget(section('Light'))
        self.ev_val = QLabel('Auto', objectName='value')
        self.auto_btn = QPushButton('Auto', objectName='ghost', clicked=self._auto_exposure)
        lay.addWidget(hbox(QLabel('Exposure'), 'stretch', self.ev_val, self.auto_btn, spacing=4))
        self.ev = QSlider(Qt.Horizontal); self.ev.setRange(-200, 300); self.ev.setSingleStep(5); self.ev.setPageStep(25)
        self.ev.valueChanged.connect(self._on_ev)
        lay.addWidget(self.ev)
        lay.addWidget(hint('Auto sets exposure a little brighter than the camera preview.'))

        lay.addWidget(section('Look'))
        self.look = Toggle('Vanyajeev wildlife look'); self.look.toggled.connect(self._on_look)
        lay.addWidget(self.look)
        lay.addWidget(hint('Recovers highlights, opens shadows, adds clarity and warmth. Off by default for JPEGs.'))
        self.finish = Toggle('Subject finishing'); self.finish.toggled.connect(self._on_finish)
        lay.addWidget(self.finish)
        lay.addWidget(hint('Finds the animal, lifts it, calms the background, sharpens face and eyes.'))

        lay.addWidget(section('Composition'))
        self.aspect = QComboBox(); [self.aspect.addItem(n) for n, _ in ASPECTS]; self.aspect.setFixedWidth(150)
        self.aspect.currentIndexChanged.connect(self._on_aspect)
        lay.addWidget(hbox(QLabel('Crop ratio'), 'stretch', self.aspect))
        row = QWidget(); g = QHBoxLayout(row); g.setContentsMargins(0, 0, 0, 0); g.setSpacing(6)
        for label, slot in (('Reset crop', self._reset_crop), ('Auto subject', self._reset_subject), ('Clear face', self._clear_face)):
            b = QPushButton(label, clicked=slot); b.setStyleSheet('padding: 6px 4px;'); b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            g.addWidget(b, 1)
        lay.addWidget(row)
        lay.addWidget(hint('Tip: place the animal on a thirds line with open space in the direction it looks or moves.'))

        lay.addWidget(section('Output'))
        self.print_cb = QComboBox(); [self.print_cb.addItem(n) for n, _ in PRINT]; self.print_cb.setFixedWidth(190)
        self.print_cb.setCurrentIndex(int(self.settings.value('print', 2)))
        self.print_cb.currentIndexChanged.connect(lambda i: (self.settings.setValue('print', i), self._update_info()))
        lay.addWidget(hbox(QLabel('Print size'), 'stretch', self.print_cb))
        self.sig_on = Toggle('Sign exported photos'); self.sig_on.setChecked(self.settings.value('sig_on', 'false') == 'true')
        self.sig_on.toggled.connect(lambda v: self.settings.setValue('sig_on', 'true' if v else 'false'))
        lay.addWidget(self.sig_on)
        self.sig_label = QLabel(self._sig_text(), objectName='hint'); self.sig_label.setWordWrap(True)
        lay.addWidget(self.sig_label)
        lay.addWidget(hbox(QPushButton('Choose signature…', clicked=self._choose_sig), 'stretch'))
        self.artist = QLineEdit(self.settings.value('artist', '')); self.artist.setPlaceholderText('Photographer name (copyright)')
        self.artist.textChanged.connect(lambda t: self.settings.setValue('artist', t))
        lay.addWidget(self.artist)
        self.out_label = QLabel(self._out_text(), objectName='hint'); self.out_label.setWordWrap(True)
        lay.addWidget(self.out_label)
        lay.addWidget(hbox(QPushButton('Change folder…', clicked=self._choose_out), QPushButton('Reset', objectName='ghost', clicked=lambda: (self.settings.setValue('out_dir', ''), self.out_label.setText(self._out_text()))), 'stretch'))
        self.info = QLabel('', objectName='info'); self.info.setWordWrap(True)
        lay.addSpacing(6); lay.addWidget(self.info)
        lay.addStretch(1)
        lay.addWidget(QLabel(f'{APP} {VERSION}', objectName='hint'))
        return f

    # ------------------------------------------------------------------ library
    def add_files(self):
        exts = ' '.join(f'*{e}' for e in sorted(E.SUPPORTED)) + ' ' + ' '.join(f'*{e.upper()}' for e in sorted(E.SUPPORTED))
        files, _ = QFileDialog.getOpenFileNames(self, 'Add photos', self.settings.value('last_dir', ''), f'Photos ({exts})')
        if files:
            self.settings.setValue('last_dir', str(Path(files[0]).parent))
            self.add_paths(files)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, 'Add folder', self.settings.value('last_dir', ''))
        if d:
            self.settings.setValue('last_dir', d)
            self.add_paths([d])

    def add_paths(self, paths):
        found = []
        for p in map(Path, paths):
            if p.is_dir():
                found += sorted(f for f in p.rglob('*') if f.suffix.lower() in E.SUPPORTED and 'Processed' not in f.parts)
            elif p.suffix.lower() in E.SUPPORTED:
                found.append(p)
        known = {ph.path for ph in self.photos}
        new = [f for f in found if f not in known]
        # if a RAW and its camera JPEG share a name, keep the RAW only
        raws = {f.with_suffix('').as_posix().lower() for f in new if E.is_raw(f)}
        new = [f for f in new if E.is_raw(f) or f.with_suffix('').as_posix().lower() not in raws]
        for f in new:
            ph = E.new_photo(f)
            self.photos.append(ph)
            it = QListWidgetItem(ph.name); it.setData(Qt.UserRole, len(self.photos) - 1)
            it.setSizeHint(QSize(196, 150)); it.setTextAlignment(Qt.AlignHCenter | Qt.AlignBottom)
            self.list.addItem(it)
            job = Job(E.thumbnail, f)
            job.s.done.connect(lambda a, it=it: it.setIcon(QIcon(QPixmap.fromImage(to_qimage(a)))))
            self._start(job)
        self.count.setText(str(len(self.photos)))
        if new and self.current is None:
            self.list.setCurrentRow(0)
        self.status.setText(f'Added {len(new)} photo(s)' if new else 'No new photos found')
        self._sync_controls()

    def _remove(self):
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}, reverse=True)
        for r in rows:
            self.list.takeItem(r); self.photos.pop(r)
        for i in range(self.list.count()):
            self.list.item(i).setData(Qt.UserRole, i)
        self.count.setText(str(len(self.photos)))
        if not self.photos:
            self.current = None; self.canvas.clear()
        self._sync_controls()

    def _select(self, row):
        if row < 0 or row >= len(self.photos):
            self.current = None; self.canvas.clear(); self._sync_controls(); return
        self.current = self.photos[row]
        self.mask_cache = {}
        self.canvas.clear()
        self._load_canvas_state()
        self._sync_controls()
        self._render(now=True)

    # ------------------------------------------------------------------ controls <-> settings
    def _load_canvas_state(self):
        s = self.current.settings
        self.canvas.crop, self.canvas.subject, self.canvas.face = s.crop, s.subject, s.face

    def _sync_controls(self):
        has = self.current is not None
        for w in (self.ev, self.auto_btn, self.look, self.finish, self.aspect, self.export_sel):
            w.setEnabled(has and not self.exporting)
        self.export_all.setEnabled(bool(self.photos) and not self.exporting)
        self.remove_btn.setEnabled(bool(self.photos) and not self.exporting)
        for b in self.mode_btns.values():
            b.setEnabled(has)
        if not has:
            self.title.setText('No photo selected'); self.info.setText('Add photos to begin.'); return
        s = self.current.settings
        self.title.setText(self.current.name)
        for w, val in ((self.look, s.look), (self.finish, s.finish)):
            w.blockSignals(True); w.setChecked(val); w.blockSignals(False)
        self.ev.blockSignals(True)
        ev = s.exposure if s.exposure is not None else (self.current.auto_ev or 0.0)
        self.ev.setValue(int(round(ev * 100)))
        self.ev.blockSignals(False)
        self.ev_val.setText(f'{ev:+.2f} EV' + ('  (auto)' if s.exposure is None else ''))
        self._update_info()

    def _update_info(self):
        if not self.current:
            return
        s = self.current.settings
        img = self.canvas.after
        if img is None:
            self.info.setText('Rendering…'); return
        # estimate full-resolution output size from the preview's aspect and the source size
        full = getattr(self.current, '_full_size', None)
        if full is None:
            try:
                if self.current.raw:
                    full = (6000, 4000)
                else:
                    from PIL import Image
                    full = Image.open(self.current.path).size
            except Exception:
                full = (img.width(), img.height())
            self.current._full_size = full
        W, H = full
        if s.crop:
            W, H = int(W * s.crop[2]), int(H * s.crop[3])
        f = PRINT[self.print_cb.currentIndex()][1]
        lines = [f'Photo     {W:,} × {H:,} px   ({W / 300:.1f} × {H / 300:.1f} in)']
        if f:
            lines.append(f'Print     {W * f:,} × {H * f:,} px   ({W * f / 300:.1f} × {H * f / 300:.1f} in)')
        lines.append('Sizes at 300 ppi')
        self.info.setText('\n'.join(lines))

    def _changed(self, reset_ev=False, reset_mask=False):
        if not self.current:
            return
        if reset_ev:
            self.current.auto_ev = None
        if reset_mask:
            self.mask_cache = {}
        self.render_timer.start()

    def _on_ev(self, v):
        self.current.settings.exposure = v / 100.0
        self.ev_val.setText(f'{v / 100:+.2f} EV')
        self._changed()

    def _auto_exposure(self):
        self.current.settings.exposure = None
        self._changed(reset_ev=True)

    def _on_look(self, v):
        self.current.settings.look = v
        self.current.settings.exposure = None
        self._changed(reset_ev=True)

    def _on_finish(self, v):
        self.current.settings.finish = v
        self._changed()

    def _on_aspect(self, i):
        self.canvas.aspect = ASPECTS[i][1]

    def _on_crop(self, c):
        self.current.settings.crop = tuple(round(x, 4) for x in c) if c else None
        self.current.settings.subject = None   # subject/face are relative to the crop
        self.current.settings.face = None
        self.canvas.subject = self.canvas.face = None
        self._changed(reset_ev=True, reset_mask=True)

    def _on_subject(self, b):
        self.current.settings.subject = tuple(round(x, 4) for x in b) if b else None
        self._changed(reset_mask=True)

    def _on_face(self, p):
        self.current.settings.face = tuple(round(x, 4) for x in p) if p else None
        self._changed()

    def _reset_crop(self):
        if self.current:
            self.canvas.crop = None
            self._on_crop(None)

    def _reset_subject(self):
        if self.current:
            self.canvas.subject = None
            self._on_subject(None)

    def _clear_face(self):
        if self.current:
            self.canvas.face = None
            self._on_face(None)

    def _mode_btn(self, k):
        if self.current:
            self.mode_btns[k].setChecked(True); self._set_mode(k)

    def _set_mode(self, k):
        prev = self.canvas.mode
        self.canvas.set_mode(k)
        self.mode_hint.setText({'view': '', 'crop': 'Drag to crop · thirds grid shown · switch to View to see the result',
                                'subject': 'Drag a box around the animal · gold tint = detected subject',
                                'face': 'Click between the eyes'}[k])
        if self.current and ((prev == 'crop') != (k == 'crop')):
            self._render(now=True)

    def _toggle_compare(self, v):
        self.canvas.compare = v
        if v and self.canvas.mode != 'view':
            self._mode_btn('view')
        self.canvas.update()

    # ------------------------------------------------------------------ rendering
    def _render(self, now=False):
        if not self.current:
            return
        self.gen += 1
        gen, ph = self.gen, self.current
        uncropped = self.canvas.mode == 'crop'
        self.canvas.busy = True; self.canvas.update()
        job = Job(E.render_preview, ph, 1800, uncropped, self.mask_cache)
        job.s.done.connect(lambda r, gen=gen, ph=ph: self._rendered(r, gen, ph))
        job.s.fail.connect(lambda m: (setattr(self.canvas, 'busy', False), self.status.setText(f'Preview failed: {m}')))
        self._start(job)

    def _rendered(self, r, gen, ph):
        if gen != self.gen or ph is not self.current:
            return
        before, after, mask = r
        self.canvas.busy = False
        self.canvas.set_images(before, after, mask)
        self._sync_controls()

    # ------------------------------------------------------------------ output settings
    def _sig_text(self):
        p = self.settings.value('signature', '')
        return f'Signature: {Path(p).name}' if p else 'Signature: none chosen (transparent PNG)'

    def _choose_sig(self):
        f, _ = QFileDialog.getOpenFileName(self, 'Choose signature (transparent PNG)', '', 'PNG (*.png)')
        if f:
            self.settings.setValue('signature', f); self.sig_label.setText(self._sig_text()); self.sig_on.setChecked(True)

    def _out_text(self):
        d = self.settings.value('out_dir', '')
        return f'Save to: {d}' if d else 'Save to: a "Processed" folder next to each photo'

    def _choose_out(self):
        d = QFileDialog.getExistingDirectory(self, 'Choose output folder')
        self.settings.setValue('out_dir', d or '')
        self.out_label.setText(self._out_text())

    def _open_output(self):
        if getattr(self, '_last_out', None):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_out)))

    # ------------------------------------------------------------------ export
    def export_selected(self):
        rows = sorted({self.list.row(i) for i in self.list.selectedItems()}) or ([self.list.currentRow()] if self.current else [])
        self._export([self.photos[r] for r in rows if r >= 0])

    def export_everything(self):
        self._export(list(self.photos))

    def _export(self, photos):
        if not photos or self.exporting:
            return
        sig = self.settings.value('signature', '') if self.sig_on.isChecked() else ''
        if self.sig_on.isChecked() and not sig:
            QMessageBox.information(self, APP, 'Choose a signature PNG first, or turn off "Sign exported photos".'); return
        opts = E.ExportOptions(out_dir=self.settings.value('out_dir', '') or None,
                               print_factor=PRINT[self.print_cb.currentIndex()][1],
                               signature=sig or None, artist=self.artist.text().strip())
        self.exporting = True; self._sync_controls()
        self.prog.setValue(0); self.prog.show(); self.open_btn.hide()
        n = len(photos)

        def work(sig_obj):
            out = []
            for i, ph in enumerate(photos):
                def cb(msg, frac, i=i, ph=ph):
                    sig_obj.progress.emit(f'{ph.name} · {msg}  ({i + 1}/{n})', (i + frac) / n)
                try:
                    out += E.export(ph, opts, cb)
                except Exception as e:
                    traceback.print_exc()
                    ph.status = f'error: {e}'
            return out

        job = Job(lambda: work(job.s))
        job.s.progress.connect(lambda m, f: (self.status.setText(m), self.prog.setValue(int(f * 100))))
        job.s.done.connect(lambda out: self._exported(out, photos))
        job.s.fail.connect(lambda m: self._exported([], photos, m))
        self._start(job)

    def _exported(self, out, photos, err=None):
        self.exporting = False; self.prog.hide()
        bad = [p for p in photos if p.status.startswith('error')]
        if out:
            self._last_out = Path(out[0]).parent
            self.open_btn.show()
        for i in range(self.list.count()):
            ph = self.photos[i]
            self.list.item(i).setText(('✓  ' if ph.status == 'done' else '⚠  ' if ph.status.startswith('error') else '') + ph.name)
        msg = f'Exported {len(photos) - len(bad)} of {len(photos)} photo(s) · {len(out)} file(s) written'
        if bad or err:
            msg += f' · {len(bad)} failed' + (f' ({err})' if err else '')
        self.status.setText(msg)
        self._sync_controls()

    # ------------------------------------------------------------------ window drag & drop
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.add_paths([u.toLocalFile() for u in e.mimeData().urls()])


def main():
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Vanyajeev.App')
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setStyle('Fusion')
    theme.apply_palette(app)
    app.setStyleSheet(theme.QSS)
    w = MainWindow()
    w.show()
    if len(sys.argv) > 1:
        w.add_paths(sys.argv[1:])
    sys.exit(app.exec())
