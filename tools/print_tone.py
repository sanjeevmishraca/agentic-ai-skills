#!/usr/bin/env python3
"""
print_tone.py - WAT Framework Tool - final tone pass for wall prints
Version 1.0.0 - 2026-11-23

Why: the house look (Shadows +76, Blacks lifted by the finish) kept sunlit, high-key scenes too
white and milky - rhinos in sun, eland, pale grassland (Laikipia 8473, 8397, 8387, 9125, 8995,
8612). Images the photographer approved had a luminance median of ~105-127 and real blacks
(2nd percentile <= ~20); the rejected ones sat at median 143-159 with grey "blacks" (p2 26-76).

What it does (luminance-ratio, so hue and saturation are preserved):
  1. Black anchor  - if the 0.5th percentile is above BLACK_TARGET, stretch so it lands there
                     (true black for print; highlights stay put).
  2. Midtone cap   - if the median is above MID_MAX, a gamma pulls it down to MID_TARGET
                     (darker, richer mid-tones; whites barely move).
  3. Shoulder     - if the 98th percentile is above 200, roll off highlights above 0.62 (slope 0.8)
                     so sunlit faces, horns and pale coats keep detail instead of reading white.
  4. Warmth        - optional: +warm shifts toward golden (R up, B down), e.g. 0.04 for leopards.
Scenes already in range are left untouched, so dark/low-key images (black leopard, dusk) are not
crushed.

Usage
  python tools/print_tone.py IN OUT [--mid-target 120] [--mid-max 128] [--black 4] [--warm 0.0]
  from print_tone import tone;  arr = tone(arr_float01, warm=0.04)
"""
import argparse, sys
import numpy as np

BLACK_TARGET = 4 / 255
MID_MAX = 128 / 255
MID_TARGET = 120 / 255
SHOULDER_IF = 200 / 255      # apply the roll-off only if the 98th percentile is above this
SHOULDER_KNEE = 0.62
SHOULDER_SLOPE = 0.80


def _luma(a):
    return a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722


def decool(a, strength=0.85):
    """Remove the cyan/teal cast that skylight + dehaze leave on white/pale fur (Laikipia 0059, 0093
    leopard muzzles looked teal at 100 %). Targets pixels where green AND blue exceed red; sky-blue
    (blue clearly above green) is left alone. Pulls them to a neutral-warm grey of equal luminance."""
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    cyan = np.clip((np.minimum(g, b) - r) / 0.05, 0, 1)
    skyish = np.clip((b - g - 0.03) / 0.05, 0, 1)
    w = (cyan * (1 - skyish) * strength)[..., None]
    L = _luma(a)[..., None]
    warmgrey = L * np.array([1.025, 1.0, 0.95], np.float32)
    return np.clip(a * (1 - w) + warmgrey * w, 0, 1)


def tone(a, mid_target=MID_TARGET, mid_max=MID_MAX, black=BLACK_TARGET, warm=0.0, report=None, shoulder=True):
    """a: float RGB 0..1. Returns a new float array."""
    a = np.clip(a.astype(np.float32), 0, 1)
    L = _luma(a)
    small = L[::4, ::4]
    p05, med, p995 = np.percentile(small, [0.5, 50, 99.5])
    Ln = L.copy()
    did = []
    if p05 > black + 2 / 255:
        top = max(p995, p05 + 0.2)
        Ln = np.clip(black + (Ln - p05) * (top - black) / (top - p05), 0, None)
        med = black + (med - p05) * (top - black) / (top - p05)
        did.append(f'black {p05*255:.0f}->{black*255:.0f}')
    if med > mid_max:
        g = np.log(mid_target) / np.log(med)          # med**g == mid_target
        Ln = np.power(np.clip(Ln, 1e-6, 1), g)
        did.append(f'median {med*255:.0f}->{mid_target*255:.0f}')
    # 3. Highlight shoulder: sunlit faces/horns/pale coats were reading as "white" - roll off the
    #    top so detail stays in light-coloured animals (only when the bright end is high).
    p98 = np.percentile(Ln[::4, ::4], 98)
    if shoulder and p98 > SHOULDER_IF:
        knee = SHOULDER_KNEE
        Ln = np.where(Ln > knee, knee + (Ln - knee) * SHOULDER_SLOPE, Ln)
        did.append(f'highlights p98 {p98*255:.0f}->{(knee + (p98-knee)*SHOULDER_SLOPE)*255:.0f}')
    out = a * (Ln / np.maximum(L, 1e-6))[..., None]
    if warm:
        out = out * np.array([1 + warm, 1 + warm * 0.25, 1 - warm], np.float32)
        did.append(f'warm {warm:+.2f}')
    if report is not None:
        report.append(', '.join(did) or 'in range, unchanged')
    return np.clip(out, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--mid-target', type=float, default=MID_TARGET * 255)
    ap.add_argument('--mid-max', type=float, default=MID_MAX * 255)
    ap.add_argument('--black', type=float, default=BLACK_TARGET * 255)
    ap.add_argument('--warm', type=float, default=0.0)
    a = ap.parse_args()
    from PIL import Image
    im = Image.open(a.src)
    info = {k: im.info[k] for k in ('icc_profile', 'dpi', 'exif') if k in im.info}
    arr = np.asarray(im.convert('RGB')).astype(np.float32) / 255
    rep = []
    out = tone(arr, a.mid_target / 255, a.mid_max / 255, a.black / 255, a.warm, rep)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8)).save(a.dst, quality=97, subsampling=0, **info)
    print(f'{a.src}: {rep[0]}')


if __name__ == '__main__':
    main()
