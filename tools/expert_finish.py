#!/usr/bin/env python3
"""
expert_finish.py - wildlife "expert finish" (local edits a fine-art processor would add).

Applied after the house-look development (photo_develop.py), on a lossless PNG:
  1. Subject mask      GrabCut seeded from a subject box (or automatic saliency box)
  2. Background        calmer: slight desaturation of red/orange earth, gentle burn
                       with a graduated top band, kept lighter in a soft pool around the subject
  3. Subject dodge     luminance-ratio lift of the animal's midtones (hue/chroma preserved);
                       dark rosettes/markings excluded so they stay rich black
  4. Local WB          warms shaded fur that picked up blue skylight; keeps the golden coat
  5. Face & eyes       local clarity + fine sharpening on the face, small eye-catch lift
  6. Markings          removes the blue skylight cast from dark markings (neutral black / warm brown)

Usage
  python expert_finish.py IN.png OUT.png|OUT.jpg [--subject x,y,w,h] [--face x,y] [--mask mask.png]
    --subject  subject box as fractions of the image (0-1). Omit for an automatic saliency box.
    --face     face centre as fractions of the image (0-1). Omit to skip face/eye work.
    --mask     use an existing subject mask instead of GrabCut (white = subject).
"""
import argparse
import numpy as np
import cv2
from PIL import Image

REF_W = 5190.0   # face/eye radii and feathering were tuned at this width; scaled to the image


def _luma(a):
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def auto_subject_box(rgb_u8):
    """Saliency-based subject box (fractions). Falls back to a centre box."""
    small = cv2.resize(rgb_u8, (512, int(512 * rgb_u8.shape[0] / rgb_u8.shape[1])))
    try:
        sal = cv2.saliency.StaticSaliencyFineGrained_create()
        ok, smap = sal.computeSaliency(cv2.cvtColor(small, cv2.COLOR_RGB2BGR))
        smap = (smap * 255).astype(np.uint8) if smap.dtype != np.uint8 else smap
        smap = cv2.GaussianBlur(smap, (0, 0), 6)
        _, th = cv2.threshold(smap, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(th)
        if ok and n > 1:
            i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            x, y, w, h = stats[i, :4]
            H, W = th.shape
            pad = 0.05
            return (max(0, x / W - pad), max(0, y / H - pad),
                    min(1, w / W + 2 * pad), min(1, h / H + 2 * pad))
    except Exception:
        pass
    return (0.25, 0.15, 0.5, 0.75)


def subject_mask(rgb_u8, box):
    """GrabCut subject mask (float 0..1, full size), computed at quarter resolution."""
    H, W = rgb_u8.shape[:2]
    s = 0.25
    small = cv2.resize(rgb_u8, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    bx, by, bw, bh = box
    rect = (max(1, int(bx * w)), max(1, int(by * h)),
            max(2, min(w - 2, int(bw * w))), max(2, min(h - 2, int(bh * h))))
    m = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), m, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:                                         # keep the largest blob = the animal
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(lab == i, 255, 0).astype(np.uint8)
    return cv2.resize(fg, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255


def expert_finish(y, m, face=None):
    """y: RGB float 0..1, m: subject mask 0..1, face: (x, y) in pixels or None."""
    H, W = y.shape[:2]
    k = W / REF_W
    mf = np.clip(cv2.GaussianBlur(m, (0, 0), 18 * k), 0, 1)              # feathered subject
    halo = np.clip(cv2.GaussianBlur(m, (0, 0), 220 * k) * 1.6, 0, 1)     # soft light pool
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # 1. Background: calmer earth tones, slightly darker, graduated top burn
    bgw = 1 - mf
    hsv = cv2.cvtColor((np.clip(y, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hue = hsv[..., 0] * 2
    red_orange = np.clip(1 - np.abs(((hue + 180) % 360 - 180) - 15) / 30, 0, 1)
    grey = _luma(y)[..., None]
    y = grey + (y - grey) * (1 - bgw * (0.02 + 0.06 * red_orange))[..., None]
    grad = np.clip(1 - yy / (0.45 * H), 0, 1) ** 1.3
    y = y * (1 - bgw * (0.03 + 0.08 * grad) * (1 - 0.6 * halo))[..., None]

    # 2. Subject dodge (luminance ratio -> hue/chroma preserved; darks excluded)
    lift = 0.22 * mf + 0.06 * halo * (1 - mf)
    Lo = np.maximum(_luma(y), 1e-4)
    keepdark = np.clip((Lo - 0.18) / 0.17, 0, 1)
    Ln = np.clip(Lo + 1.6 * lift * keepdark * Lo * (1 - Lo) ** 2, 0, 1)
    y = y * (Ln / Lo)[..., None]

    # 3. Local white balance: warm the shaded fur, keep the golden coat
    shade = mf * np.clip((0.75 - _luma(y)) / 0.5, 0, 1)
    y = y * np.stack([1 + 0.012 * mf + 0.02 * shade, 1 + 0.004 * mf, 1 - 0.02 * mf - 0.05 * shade], -1)

    # 4. Face & eyes
    if face is not None:
        FX, FY = face
        def radial(cx, cy, rx, ry):
            return np.clip(1 - ((xx - cx) / rx) ** 2 - ((yy - cy) / ry) ** 2, 0, 1) ** 1.5
        fmask = radial(FX, FY, 330 * k, 300 * k) * np.maximum(mf, 0.3)
        eyes = radial(FX + 105 * k, FY - 45 * k, 150 * k, 70 * k)
        Ly = _luma(np.clip(y, 0, 1))
        det = Ly - cv2.GaussianBlur(Ly, (0, 0), 12 * k)
        y = y + (0.22 * fmask * det)[..., None]
        fine = y - cv2.GaussianBlur(y, (0, 0), 1.2)
        y = y + fine * (0.15 * fmask)[..., None]
        Le = np.maximum(_luma(np.clip(y, 0, 1)), 1e-4)
        y = y * ((Le + 0.20 * eyes * Le * (1 - Le)) / Le)[..., None]

    # 5. Dark markings: strip the skylight-blue cast
    Ld = _luma(np.clip(y, 0, 1))
    dk = mf * np.clip((0.40 - Ld) / 0.25, 0, 1)
    y = y + (Ld[..., None] - y) * (0.75 * dk)[..., None]
    y = y * np.stack([1 + 0.04 * dk, 1 + 0.01 * dk, 1 - 0.04 * dk], -1)
    return np.clip(y, 0, 1)


def run(src, dst, subject=None, face=None, mask_path=None):
    pil = Image.open(src)
    info = {k: pil.info[k] for k in ('icc_profile', 'exif', 'dpi') if k in pil.info}
    u8 = np.asarray(pil.convert('RGB'))
    H, W = u8.shape[:2]
    if mask_path:
        m = cv2.resize(cv2.imread(mask_path, 0), (W, H)).astype(np.float32) / 255
    else:
        m = subject_mask(u8, subject or auto_subject_box(u8))
    fpx = (face[0] * W, face[1] * H) if face else None
    y = expert_finish(u8.astype(np.float32) / 255, m, fpx)
    out = Image.fromarray((y * 255 + 0.5).astype(np.uint8))
    if str(dst).lower().endswith('.png'):
        out.save(dst, 'PNG', **{k: v for k, v in info.items() if k in ('icc_profile', 'dpi')})
    else:
        out.save(dst, 'JPEG', quality=97, subsampling=0, **info)
    return dst


def _frac(s, n):
    v = [float(t) for t in s.split(',')]
    assert len(v) == n
    return tuple(v)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--subject', help='x,y,w,h fractions')
    ap.add_argument('--face', help='x,y fractions')
    ap.add_argument('--mask')
    a = ap.parse_args()
    run(a.inp, a.out, _frac(a.subject, 4) if a.subject else None,
        _frac(a.face, 2) if a.face else None, a.mask)
    print('saved', a.out)
