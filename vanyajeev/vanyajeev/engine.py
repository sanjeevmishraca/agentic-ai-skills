"""
Vanyajeev processing engine.

Wraps the verified raw-to-jpeg v3 pipeline (tools/) so the app produces exactly the same result:
  develop (house look)  ->  expert finish  ->  print upscale  ->  signature

Coordinates follow the pipeline convention:
  crop     x, y, w, h  fractions of the FULL frame
  subject  x, y, w, h  fractions of the CROPPED frame
  face     x, y        fractions of the CROPPED frame
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import cv2
from PIL import Image, ImageCms, ImageStat

# --- locate the pipeline modules (repo layout in dev, bundled folder when frozen)
_here = Path(__file__).resolve().parent
for cand in (_here / "pipeline", _here.parent.parent / "tools"):
    if (cand / "photo_develop.py").exists():
        sys.path.insert(0, str(cand))
        break

import photo_develop as pdv          # noqa: E402
import expert_finish as efx          # noqa: E402
import upscale_print as ups          # noqa: E402

RAW_EXT = {'.cr2', '.cr3', '.nef', '.nrw', '.arw', '.raf', '.dng', '.orf', '.rw2',
           '.pef', '.srw', '.3fr', '.mef', '.mrw', '.rwl', '.x3f', '.erf'}
IMG_EXT = {'.jpg', '.jpeg', '.png', '.tif', '.tiff'}
SUPPORTED = RAW_EXT | IMG_EXT

_CAL = pdv.load_calib()
GAINS, LUT = _CAL['gains'], _CAL.get('lut')
SRGB_ICC = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def is_raw(path) -> bool:
    return Path(path).suffix.lower() in RAW_EXT


def srgb_to_linear(u8):
    x = u8.astype(np.float32) / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4).astype(np.float32)


# ----------------------------------------------------------------------------- settings
@dataclass
class Settings:
    exposure: float | None = None        # None = automatic
    look: bool = True                    # house look (RAW default on, JPEG default off)
    finish: bool = True                  # subject-aware expert finish
    crop: tuple | None = None
    subject: tuple | None = None         # None = automatic subject detection
    face: tuple | None = None

    def key(self):
        return (self.exposure, self.look, self.finish, self.crop, self.subject, self.face)


@dataclass
class Photo:
    path: Path
    settings: Settings = field(default_factory=Settings)
    auto_ev: float | None = None
    status: str = ""                     # "", "done", "error: ..."

    @property
    def raw(self):
        return is_raw(self.path)

    @property
    def name(self):
        return self.path.name


def new_photo(path) -> Photo:
    p = Photo(Path(path))
    if not p.raw:
        p.settings.look = False          # a JPEG already carries a look; don't develop it twice
    return p


# ----------------------------------------------------------------------------- loading
class _Cache:
    """Small LRU of decoded linear images (they are large)."""

    def __init__(self, n=3):
        self.n, self.d = n, OrderedDict()

    def get(self, k, make):
        if k in self.d:
            self.d.move_to_end(k)
            return self.d[k]
        v = make()
        self.d[k] = v
        while len(self.d) > self.n:
            self.d.popitem(last=False)
        return v


_preview_cache = _Cache(4)


def thumbnail(path, size=320) -> np.ndarray:
    """Fast RGB thumbnail: embedded camera preview for RAW, downscaled image otherwise."""
    path = Path(path)
    if is_raw(path):
        import rawpy
        with rawpy.imread(str(path)) as r:
            t = r.extract_thumb()
        im = Image.open(io.BytesIO(t.data)) if t.format == rawpy.ThumbFormat.JPEG else Image.fromarray(t.data)
    else:
        im = Image.open(path)
    from PIL import ImageOps
    im = ImageOps.exif_transpose(im).convert('RGB')
    im.thumbnail((size, size))
    return np.asarray(im)


def _load_linear(path, half):
    path = Path(path)
    if is_raw(path):
        return pdv.render_linear(str(path), half=half)
    from PIL import ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert('RGB')
    return srgb_to_linear(np.asarray(im))


def _camera_median(photo, lin_small):
    if photo.raw:
        try:
            return pdv.preview_median(str(photo.path))
        except Exception:
            return None
    return float(np.median(pdv.luma(pdv.srgb_oetf(lin_small)) * 255))


def _crop(lin, crop):
    if not crop:
        return lin
    fx, fy, fw, fh = crop
    H, W = lin.shape[:2]
    x0, y0 = int(round(fx * W)), int(round(fy * H))
    x1, y1 = int(round((fx + fw) * W)), int(round((fy + fh) * H))
    return lin[max(0, y0):min(H, y1), max(0, x0):min(W, x1)]


def _resize_max(a, max_px):
    h, w = a.shape[:2]
    s = max_px / max(h, w)
    if s >= 1:
        return a
    return cv2.resize(a, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)


def ensure_auto_ev(photo: Photo):
    if photo.auto_ev is not None:
        return photo.auto_ev
    lin = preview_linear(photo)
    small = _resize_max(_crop(lin, photo.settings.crop), 750)
    if photo.settings.look:
        photo.auto_ev = float(pdv.auto_ev(small, GAINS, LUT, _camera_median(photo, small)))
    else:
        photo.auto_ev = 0.0
    return photo.auto_ev


def preview_linear(photo: Photo):
    return _preview_cache.get(str(photo.path), lambda: _resize_max(_load_linear(photo.path, half=True), 2400))


# ----------------------------------------------------------------------------- rendering
def _develop(lin, photo: Photo, ev, full_res):
    s = photo.settings
    if s.look:
        y = pdv.develop(lin, ev, GAINS, lut=LUT)
        if full_res:
            return pdv.finish(y).astype(np.float32) / 255.0      # denoise + sharpen (full size only)
        u8 = (y * 255 + 0.5).astype(np.uint8)                    # light sharpen for the preview
        f = u8.astype(np.float32)
        return np.clip(f + (f - cv2.GaussianBlur(f, (0, 0), 1.0)) * 0.35, 0, 255) / 255.0
    return np.clip(pdv.srgb_oetf(lin * (2.0 ** ev)), 0, 1).astype(np.float32)


def _expert(y, photo: Photo, mask_cache=None):
    s = photo.settings
    u8 = (np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8)
    key = (s.crop, s.subject, u8.shape)
    if mask_cache is not None and key in mask_cache:
        m = mask_cache[key]
    else:
        m = efx.subject_mask(u8, s.subject or efx.auto_subject_box(u8))
        if mask_cache is not None:
            mask_cache.clear()
            mask_cache[key] = m
    H, W = y.shape[:2]
    face = (s.face[0] * W, s.face[1] * H) if s.face else None
    return efx.expert_finish(y.astype(np.float32), m, face), m


def render_preview(photo: Photo, max_px=1800, uncropped=False, mask_cache=None):
    """Returns (before_u8, after_u8, mask or None). `uncropped` shows the full frame (crop tool)."""
    lin = preview_linear(photo)
    if not uncropped:
        lin = _crop(lin, photo.settings.crop)
    lin = _resize_max(lin, max_px)
    ev = photo.settings.exposure if photo.settings.exposure is not None else ensure_auto_ev(photo)
    before = np.clip(pdv.srgb_oetf(lin * (2.0 ** (ev * (GAINS['exp'] if photo.settings.look else 1.0)))), 0, 1)
    after = _develop(lin, photo, ev, full_res=False)
    mask = None
    if photo.settings.finish and not uncropped:
        after, mask = _expert(after, photo, mask_cache)
    to8 = lambda a: (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)
    return to8(before), to8(after), mask


# ----------------------------------------------------------------------------- signature
def load_signature(png_path):
    """One transparent PNG -> (black, white) variants that keep its alpha shape."""
    im = Image.open(png_path).convert('RGBA')
    a = im.getchannel('A')
    if a.getextrema() == (255, 255):                 # no transparency: treat dark pixels as ink
        a = Image.eval(im.convert('L'), lambda v: 255 - v)
    black = Image.new('RGBA', im.size, (0, 0, 0, 0)); black.putalpha(a)
    white = Image.new('RGBA', im.size, (255, 255, 255, 0)); white.putalpha(a)
    return black, white


def apply_signature(img: Image.Image, sig, width=0.0525, margin=0.01, opacity=0.85):
    black, white = sig
    base = img.convert('RGBA')
    W, H = base.size
    L = max(W, H)
    sw = max(8, int(L * width))
    sh = max(4, int(black.height * sw / black.width))
    m = int(L * margin)
    x, y = W - sw - m, H - sh - m
    lum = ImageStat.Stat(base.crop((x, y, x + sw, y + sh)).convert('L')).mean[0]
    s = (white if lum < 128 else black).resize((sw, sh), Image.LANCZOS)
    s.putalpha(s.getchannel('A').point(lambda v: int(v * opacity)))
    base.alpha_composite(s, (x, y))
    return base.convert('RGB')


# ----------------------------------------------------------------------------- export
@dataclass
class ExportOptions:
    out_dir: Path | None = None          # None = <source folder>/Processed
    print_factor: float = 3.0            # 0 = no print master
    signature: str | None = None         # path to a transparent PNG
    artist: str = ""


def _save_jpeg(u8_or_img, dst, quality, artist=""):
    im = u8_or_img if isinstance(u8_or_img, Image.Image) else Image.fromarray(u8_or_img)
    ex = im.getexif()
    if artist:
        ex[0x013B] = artist
        ex[0x8298] = f'Copyright {artist}'
    ex[0x0131] = 'Vanyajeev'
    im.save(dst, 'JPEG', quality=quality, subsampling=0, dpi=(300, 300), icc_profile=SRGB_ICC, exif=ex)


def export(photo: Photo, opts: ExportOptions, progress=lambda msg, frac: None):
    """Full-resolution export. Returns list of written paths."""
    s = photo.settings
    out_dir = Path(opts.out_dir) if opts.out_dir else photo.path.parent / 'Processed'
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = photo.path.stem
    progress('Developing', 0.05)
    lin = _crop(_load_linear(photo.path, half=False), s.crop)
    ev = s.exposure if s.exposure is not None else ensure_auto_ev(photo)
    y = _develop(lin, photo, ev, full_res=True)
    del lin
    if s.finish:
        progress('Finishing', 0.45)
        y, _ = _expert(y, photo)
    u8 = (np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8)
    del y
    sig = load_signature(opts.signature) if opts.signature else None
    written = []
    std = out_dir / f'{stem}_vanyajeev.jpg'
    _save_jpeg(u8, std, 97, opts.artist)
    written.append(std)
    if sig:
        (out_dir / 'signed').mkdir(exist_ok=True)
        dst = out_dir / 'signed' / std.name
        _save_jpeg(apply_signature(Image.fromarray(u8), sig), dst, 97, opts.artist)
        written.append(dst)
    if opts.print_factor and opts.print_factor > 1:
        progress('Upscaling for print', 0.65)
        f = opts.print_factor
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / 'in.png'
            Image.fromarray(u8).save(src, icc_profile=SRGB_ICC)
            del u8
            pr = out_dir / f'{stem}_vanyajeev_print{int(f)}x.jpg'
            ups.upscale(str(src), str(pr), f)
        written.append(pr)
        if sig:
            progress('Signing', 0.92)
            dst = out_dir / 'signed' / pr.name
            _save_jpeg(apply_signature(Image.open(pr), sig), dst, 100, opts.artist)
            written.append(dst)
    progress('Done', 1.0)
    photo.status = 'done'
    return written
