#!/usr/bin/env python3
"""
eye_sharpen.py - WAT Framework Tool - tack-sharp eyes, nothing else touched
Version 1.0.0 - 2026-11-23

Standing rule from the photographer: on EVERY wildlife image the animal's eyes must be tack sharp,
and they must still look natural (Laikipia 9505: the far eye looked "weird" after global clarity +
dark-marking neutralisation had turned tear specks into bright dots and the iris grey-black).

For each eye (centre x, y and radius r in pixels of the image being sharpened):
  1. Speck clean (optional, --despeck): tiny isolated highlights inside the eye that are much
     brighter than their surroundings (tears, dust, processing pops) are pulled down to the
     local median, so sharpening can't turn them into white dots.
  2. Tone restore (optional, --restore R,G,B strength): blends the eye's colour toward a
     natural iris tint where the finish neutralised it to grey/black.
  3. Sharpen: luminance-only unsharp mask at the eye's own detail scale (radius ~r/40, strong) plus
     fine micro-contrast, inside a feathered circular mask; overshoot is clamped to the local
     min/max so no halos or bright rims appear.

Usage
  python tools/eye_sharpen.py IN OUT --eye x,y,r [--eye x,y,r ...] [--amount 1.6] [--despeck]
  coordinates may be fractions (all values <= 1) or pixels.
"""
import argparse
import numpy as np
import cv2


def _parse_eye(s, W, H):
    x, y, r = [float(t) for t in s.split(',')]
    if max(x, y, r) <= 1.0:
        x, y, r = x * W, y * H, r * W
    return x, y, r


def sharpen_eyes(rgb_u8, eyes, amount=1.6, despeck=False, restore=None):
    """rgb_u8: HxWx3 uint8 RGB. eyes: [(x, y, r) px]. Returns uint8 RGB."""
    img = rgb_u8.astype(np.float32) / 255
    H, W = img.shape[:2]
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)            # L 0..100
    L = lab[..., 0].copy()
    for (x, y, r) in eyes:
        pad = int(r * 2.2) + 8
        x0, y0, x1, y1 = max(0, int(x - pad)), max(0, int(y - pad)), min(W, int(x + pad)), min(H, int(y + pad))
        sub = L[y0:y1, x0:x1]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.sqrt((xx - x) ** 2 + (yy - y) ** 2) / r
        m = np.clip(1.6 - d, 0, 1) ** 1.5                    # full inside r*0.6, fades out by 1.6r
        if despeck:
            med = cv2.medianBlur(np.clip(sub, 0, 100).astype(np.uint8), max(3, int(r / 6) | 1)).astype(np.float32)
            pop = np.clip(sub - med - 12, 0, None)            # >12 L brighter than local median
            sub = sub - pop * (d < 1.1)
        rad = max(0.8, r / 40)
        blur = cv2.GaussianBlur(sub, (0, 0), rad)
        fine = cv2.GaussianBlur(sub, (0, 0), max(2.0, r / 10))
        sharp = sub + amount * (sub - blur) + 0.35 * (sub - fine)
        lo = cv2.erode(sub, np.ones((3, 3), np.uint8)); hi = cv2.dilate(sub, np.ones((3, 3), np.uint8))
        sharp = np.clip(sharp, lo - 2, hi + 2)                 # clamp overshoot: no halos
        L[y0:y1, x0:x1] = sub * (1 - m) + sharp * m
        if restore is not None:
            (tr, tg, tb), k = restore
            tint = cv2.cvtColor(np.array([[[tr, tg, tb]]], np.float32) / 255, cv2.COLOR_RGB2LAB)[0, 0]
            mm = (m * k)[..., None]
            ab = lab[y0:y1, x0:x1, 1:]
            lab[y0:y1, x0:x1, 1:] = ab * (1 - mm) + tint[1:] * mm
    lab[..., 0] = L
    out = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--eye', action='append', required=True, help='x,y,r (fractions or px)')
    ap.add_argument('--amount', type=float, default=1.6)
    ap.add_argument('--despeck', action='store_true')
    ap.add_argument('--restore', help='R,G,B,strength e.g. 150,110,40,0.5')
    a = ap.parse_args()
    from PIL import Image
    im = Image.open(a.src)
    info = {k: im.info[k] for k in ('icc_profile', 'dpi', 'exif') if k in im.info}
    arr = np.asarray(im.convert('RGB'))
    H, W = arr.shape[:2]
    eyes = [_parse_eye(e, W, H) for e in a.eye]
    rest = None
    if a.restore:
        v = [float(t) for t in a.restore.split(',')]
        rest = ((v[0], v[1], v[2]), v[3])
    out = sharpen_eyes(arr, eyes, a.amount, a.despeck, rest)
    Image.fromarray(out).save(a.dst, quality=97, subsampling=0, **info)
    print(f'{a.dst}: {len(eyes)} eye(s) sharpened')


if __name__ == '__main__':
    main()
