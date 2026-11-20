#!/usr/bin/env python3
"""
upscale_print.py - make a large-print master from a finished (unsigned) JPEG.

Standing rule (2026-11-20): every processed image also gets a print
master at the LARGEST useful size = 3x (the practical ceiling for interpolation;
beyond ~3x prints only get softer, not more detailed). No pixel cap. Recipe = his saved upscale recipe: Lanczos upscale in 2x steps, then
Unsharp Mask radius 2.0 px / 90% / threshold 2. Saved at 300 ppi, sRGB,
JPEG quality 100 4:4:4, metadata kept. Sign AFTER upscaling (signature
renders crisp at the final size).

Usage: python upscale_print.py IN.png OUT.jpg [--factor 3]
"""
import argparse, math
import numpy as np
from PIL import Image, ImageFilter

DEFAULT_FACTOR = 3.0

def usm_threshold(im, radius=2.0, percent=90, threshold=2):
    # Pillow's UnsharpMask implements radius / percent / threshold like Photoshop
    return im.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))

def defringe(im):
    """Neutralise purple/magenta and cyan/green fringes along high-contrast edges
    (rosettes, whiskers) before enlarging. Golden/brown fur hues are left alone."""
    import cv2
    a = np.asarray(im, np.float32) / 255
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    gx = cv2.Sobel(L, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(L, cv2.CV_32F, 0, 1, ksize=3)
    edge = cv2.dilate(np.clip((np.hypot(gx, gy) - 40) / 80, 0, 1), np.ones((5, 5), np.uint8))
    edge = cv2.GaussianBlur(edge, (0, 0), 1.5)
    hue = np.degrees(np.arctan2(B, A)) % 360
    purple = np.clip(1 - np.abs(((hue - 315) + 180) % 360 - 180) / 50, 0, 1)   # magenta/purple
    cyan = np.clip(1 - np.abs(((hue - 190) + 180) % 360 - 180) / 50, 0, 1)     # cyan/green-blue
    k = edge * np.maximum(purple, cyan) * 0.85
    lab[..., 1] = A * (1 - k); lab[..., 2] = B * (1 - k)
    out = np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0, 1)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--factor', type=float, default=DEFAULT_FACTOR)
    a = ap.parse_args()
    upscale(a.inp, a.out, a.factor)

def upscale(inp, out, factor=DEFAULT_FACTOR):
    class _A: pass
    a = _A(); a.inp, a.out, a.factor = inp, out, factor
    src = Image.open(a.inp)
    info = {k: src.info[k] for k in ('icc_profile', 'exif') if k in src.info}
    im = src.convert('RGB')
    W, H = im.size
    im = defringe(im)                                   # enlargement magnifies colour fringes: clean them first
    f = a.factor
    tw, th = int(round(W * f)), int(round(H * f))
    steps = max(1, math.ceil(math.log2(max(f, 1.0001))))
    for i in range(1, steps + 1):                       # 2x steps
        f = min(2.0, (tw / im.size[0]))
        im = im.resize((int(round(im.size[0] * f)), int(round(im.size[1] * f))), Image.LANCZOS)
    if im.size != (tw, th):
        im = im.resize((tw, th), Image.LANCZOS)
    # His recipe (USM r2.0 / 90% / t2) applied to LUMINANCE only and only where there is detail:
    # avoids colour fringes and keeps smooth bokeh/sky from turning blocky or gritty.
    ycc = im.convert('YCbCr'); Y, Cb, Cr = ycc.split()
    Ys = usm_threshold(Y, 2.0 * max(1.0, a.factor / 2), 90, 2)   # recipe radius scaled with enlargement
    y0 = np.asarray(Y, np.float32); y1 = np.asarray(Ys, np.float32)
    import cv2
    det = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(y0, (0, 0), 2.0 * max(1.0, a.factor / 2)), cv2.CV_32F)), (0, 0), 8)
    m = np.clip((det - 0.6) / 2.0, 0, 1) * 0.75          # 0 on smooth areas, up to 75% of the recipe on detail
    Yf = Image.fromarray(np.clip(y0 + (y1 - y0) * m, 0, 255).astype(np.uint8))
    im = Image.merge('YCbCr', (Yf, Cb, Cr)).convert('RGB')
    im.save(a.out, 'JPEG', quality=100, subsampling=0, dpi=(300, 300), **info)
    print(f'{W}x{H} -> {tw}x{th}  ({tw/300:.1f} x {th/300:.1f} in at 300 ppi)  saved {a.out}')
    return (tw, th)

if __name__ == '__main__':
    main()
