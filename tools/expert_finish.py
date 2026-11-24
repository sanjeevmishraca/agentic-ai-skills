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
  7. Pale fur          removes the teal/cyan cast from white fur inside the subject

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
    s = min(0.25, 1000.0 / W)                        # ~1000 px working width: fast, and the mask is feathered anyway
    small = cv2.resize(rgb_u8, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    bx, by, bw, bh = box
    rect = (max(1, int(bx * w)), max(1, int(by * h)),
            max(2, min(w - 2, int(bw * w))), max(2, min(h - 2, int(bh * h))))
    m = np.zeros((h, w), np.uint8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), m, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # Texture guard: an animal always has texture (fur, skin, feathers); plain sky / haze does not.
    # Without this, a wide auto box lets GrabCut swallow a slab of sky, which the finish then keeps
    # brighter than the rest of the sky (hard-edged patch).
    g = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)
    tex = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(g, (0, 0), 1.0), cv2.CV_32F)), (0, 0), 4)
    textured = (tex > max(2.0, np.percentile(tex, 25))).astype(np.uint8)
    textured = cv2.dilate(textured, np.ones((3, 3), np.uint8))      # keep fur edges, but don't swallow a band of sky
    fg = fg * textured
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:                                         # keep the largest blob = the animal
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = np.where(lab == i, 255, 0).astype(np.uint8)
    # Area guard: a subject filling > 45 % of the frame means the box was too loose; keep the core
    # (strongest texture) instead of lifting half the picture.
    if (fg > 0).mean() > 0.45:
        core = (tex > np.percentile(tex[fg > 0], 50)).astype(np.uint8) * (fg > 0)
        core = cv2.morphologyEx(core.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(core)
        if n > 1:
            i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            fg = np.where(lab == i, 255, 0).astype(np.uint8)
    return cv2.resize(fg, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255


def _soft_blur(a, sigma):
    """Very wide Gaussian computed at reduced size (identical to the eye, ~50x faster on 24 MP)."""
    H, W = a.shape[:2]
    f = max(1, int(sigma // 12))
    if f == 1:
        return cv2.GaussianBlur(a, (0, 0), sigma)
    small = cv2.resize(a, (max(1, W // f), max(1, H // f)), interpolation=cv2.INTER_AREA)
    return cv2.resize(cv2.GaussianBlur(small, (0, 0), sigma / f), (W, H), interpolation=cv2.INTER_LINEAR)


def _texture_gate(y, mf):
    """1 on textured pixels (fur, skin, grass), ~0 on smooth sky/haze; computed at ~1000 px."""
    H, W = mf.shape
    s = min(1.0, 1000.0 / W)
    g = cv2.resize(_luma(np.clip(y, 0, 1)).astype(np.float32), (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    mu = cv2.GaussianBlur(g, (0, 0), 2)
    sd = np.sqrt(np.clip(cv2.GaussianBlur(g * g, (0, 0), 2) - mu * mu, 0, None))
    bg = cv2.resize(mf, (g.shape[1], g.shape[0])) < 0.05
    smooth = np.percentile(sd[bg], 30) if bg.any() else np.percentile(sd, 20)
    gate = np.clip((sd - 1.5 * smooth) / max(2.0 * smooth, 1e-3), 0, 1)
    gate = cv2.dilate(gate, np.ones((3, 3), np.uint8))
    gate = cv2.GaussianBlur(gate, (0, 0), 1.5)
    # inside the solid core of the subject keep full strength (smooth giraffe patches, black coat)
    core = cv2.erode((cv2.resize(mf, (g.shape[1], g.shape[0])) > 0.9).astype(np.uint8), np.ones((7, 7), np.uint8))
    gate = np.maximum(gate, cv2.GaussianBlur(core.astype(np.float32), (0, 0), 3))
    return np.clip(cv2.resize(gate, (W, H), interpolation=cv2.INTER_LINEAR), 0, 1)


def _edge_feather(y, m, k):
    """Subject mask feathered INSIDE the subject and snapped to image edges (no halo outside)."""
    H, W = m.shape
    # The GrabCut mask can run 20-40 px past the real edge into smooth sky; erode well past that so
    # every treatment ends INSIDE the animal and the sky beside it is treated exactly like the rest.
    r = max(6, int(45 * k))
    inner = cv2.erode((m > 0.5).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    soft = cv2.GaussianBlur(inner.astype(np.float32), (0, 0), 18 * k)
    s = min(1.0, 1600.0 / W)                                    # guided filter at ~1600 px, then upsample
    gs = cv2.resize(_luma(np.clip(y, 0, 1)).astype(np.float32), (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    ms = cv2.resize(soft, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    try:
        ms = cv2.ximgproc.guidedFilter(gs, ms, max(2, int(10 * s * k * 5)), 1e-3)
    except Exception:
        pass
    mf = cv2.resize(ms, (W, H), interpolation=cv2.INTER_LINEAR)
    return np.clip(np.minimum(mf, soft + 0.0), 0, 1)


def expert_finish(y, m, face=None):
    """y: RGB float 0..1, m: subject mask 0..1, face: (x, y) in pixels or None."""
    H, W = y.shape[:2]
    k = W / REF_W
    # Feathered subject that follows the real edge. A plain Gaussian feather spills the subject
    # dodge onto the background and leaves the background burn short of the edge, which reads as a
    # bright glow outline against smooth sky/grass (Laikipia 9283, 9769). The mask is snapped to the
    # image edges with a guided filter and its feather kept inside the subject.
    mf = _edge_feather(y, m, k)
    # Smooth-background gate: plain sky/haze next to the animal must never be lifted or spared the
    # burn (Laikipia 0192 giraffe: a light band around the head against blue sky).
    # (no texture gate: its own edge response re-created a band; the inner feather below is enough)
    halo = np.clip(_soft_blur(m, 220 * k) * 1.6, 0, 1)                   # soft light pool
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)

    # 1. Background: calmer earth tones, slightly darker, graduated top burn
    bgw = 1 - mf
    hsv = cv2.cvtColor((np.clip(y, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    hue = hsv[..., 0] * 2
    red_orange = np.clip(1 - np.abs(((hue + 180) % 360 - 180) - 15) / 30, 0, 1)
    grey = _luma(y)[..., None]
    y = grey + (y - grey) * (1 - bgw * (0.02 + 0.06 * red_orange))[..., None]
    grad = np.clip(1 - yy / (0.45 * H), 0, 1) ** 1.3
    y = y * (1 - bgw * (0.03 + 0.08 * grad))[..., None]   # even burn: easing it near the subject read as a glow

    # 2. Subject dodge (luminance ratio -> hue/chroma preserved; darks excluded)
    # The light pool around the subject is only for backgrounds DARKER than the animal; where the
    # background is already brighter (rhino against pale grass/sky) it reads as a glow halo.
    Lsub = float(np.sum(_luma(y) * mf) / max(np.sum(mf), 1e-6))
    darker_bg = np.clip((Lsub - _luma(y)) / 0.15, 0, 1)
    halo = halo * darker_bg
    lift = 0.22 * mf + 0.03 * halo * (1 - mf)
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
        inside = np.clip(mf * 2, 0, 1)            # never touch sky/background, even if --face is off
        fmask = radial(FX, FY, 330 * k, 300 * k) * inside
        eyes = radial(FX + 105 * k, FY - 45 * k, 150 * k, 70 * k) * inside
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

    # 6. Pale fur: no teal/cyan cast (skylight + dehaze turned white muzzles teal, Laikipia 0059/0093)
    import print_tone
    y = y * (1 - mf[..., None]) + print_tone.decool(np.clip(y, 0, 1)) * mf[..., None]
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
