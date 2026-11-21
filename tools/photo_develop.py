#!/usr/bin/env python3
"""
photo_develop.py - wildlife "house look" RAW development (stage 1 of raw_to_jpeg v3).

Emulates the Adobe Camera Raw (PV 15.4, Adobe Color) edit he made on
_U4A0010LeopardLaikipia.JPG and applies it to any Canon CR3:

  WB As Shot | Exposure auto (+1.15 on the reference) | Contrast +34
  Highlights -87 | Shadows +76 | Whites +9 | Blacks -34 | Clarity +24
  Dehaze +23 | Vibrance +15 | Saturation 0 | Texture 0 | Linear curve
  Lens profile + CA on | AI Denoise | Sharpen 40 / r1.0 / detail 25
  Post-crop vignette -37 (mid 50, feather 50, highlight priority)
  Output: full size, sRGB IEC61966-2.1, 300 ppi, JPEG max quality,
  Artist/Copyright "Sanjeev Mishra".

Internal gains (how strongly each slider acts) and a residual per-channel
"look" LUT were calibrated against his reference export; see calib.json.

Usage: python photo_develop.py IN.CR3 OUT.png|OUT.jpg [--exposure EV] [--crop x,y,w,h] [--half]
"""
import argparse, json, os, sys
import numpy as np, cv2, rawpy
from PIL import Image, ImageCms

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE = dict(contrast=34, highlights=-87, shadows=76, whites=9, blacks=-34,
             clarity=24, dehaze=23, vibrance=15, saturation=0,
             vignette=-37, sharpen=40, sharpen_radius=1.0, denoise=True)
# Target tone stats of his reference export (luma, 0-255) used to auto-pick exposure
TARGET = dict(p50=72.7, mean=95.0)
DEFAULT_GAINS = dict(exp=1.0, sh=1.0, hi=1.0, con=1.0, cla=1.0, dh=1.0, wb=1.0, bk=1.0, vig=1.0)

def load_calib():
    p = os.path.join(HERE, 'calib.json')
    if os.path.exists(p):
        return json.load(open(p))
    return dict(gains=DEFAULT_GAINS, lut=None)

def srgb_oetf(x):
    x = np.clip(x, 0, None)
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(x, 1 / 2.4) - 0.055)

def render_linear(path, half=False):
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, output_color=rawpy.ColorSpace.sRGB,
                              gamma=(1, 1), no_auto_bright=True, output_bps=16,
                              half_size=half, user_flip=None)
    rgb = rgb.astype(np.float32) / 65535.0
    # match ACR default crop (6000x4000 from 6032x4032)
    h, w = rgb.shape[:2]
    ch, cw = (int(round(h * 4000 / 4032)), int(round(w * 6000 / 6032)))
    y0, x0 = (h - ch) // 2, (w - cw) // 2
    return rgb[y0:y0 + ch, x0:x0 + cw]

EDGE_EPS = float(os.environ.get('RTJ_EDGE_EPS', '0.06'))   # was 0.25: halos along subject edges against bright backgrounds

def edge_aware(a, frac, eps=None):
    eps = EDGE_EPS if eps is None else eps
    h, w = a.shape[:2]
    r = max(2, int(frac * max(h, w)))
    return cv2.ximgproc.guidedFilter(a.astype(np.float32), a.astype(np.float32), r, eps)

def luma(x):
    return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]

def blur(img, frac):
    h, w = img.shape[:2]
    s = max(1.0, frac * max(h, w))
    return cv2.GaussianBlur(img, (0, 0), s)

def develop(lin, ev, g, st=STYLE, lut=None, fast=False):
    """lin: linear sRGB float. Returns display-referred float 0..1."""
    x = lin * (2.0 ** (ev * g['exp']))
    # --- Highlights / Shadows: local tone mapping in log luminance
    L = np.maximum(luma(x), 1e-6)
    logL = np.log2(L)
    base = edge_aware(logL, 0.015)              # edge-aware local average (no halos)
    t = np.clip((base + 8) / 9.0, 0, 1)         # 0 = deep shadow, 1 = highlight (~ -8..+1 EV)
    w_sh = (1 - t) ** 2
    w_hi = t ** 2
    dlog = (st['shadows'] / 100.0) * 1.6 * g['sh'] * w_sh + (st['highlights'] / 100.0) * 1.6 * g['hi'] * w_hi
    x = x * (2.0 ** dlog)[..., None]
    # --- to display
    y = srgb_oetf(x)
    # --- Whites / Blacks endpoints
    bk = -st['blacks'] / 100.0 * 0.08 * g['bk']          # -34 -> pull black point up (crush)
    wt = 1.0 - st['whites'] / 100.0 * 0.15 * g['wb']     # +9 -> white point slightly lower (brighter)
    y = (y - bk) / max(wt - bk, 1e-3)
    # --- Contrast S-curve (Adobe Color adds a little on its own; folded into gain)
    c = st['contrast'] / 100.0 * g['con']
    yc = np.clip(y, 0, 1)
    s = yc - c * 0.5 * np.sin(2 * np.pi * yc) / (2 * np.pi) * 2
    y = np.where((y >= 0) & (y <= 1), s, y)
    # --- Dehaze: lift contrast + remove veil estimated from dark channel
    dh = st['dehaze'] / 100.0 * g['dh']
    if dh:
        dark = blur(np.min(np.clip(y, 0, 1), axis=2), 0.01)
        veil = np.percentile(dark, 1)
        y = (y - dh * 0.5 * veil) / (1 - dh * 0.5 * veil)
        m = 0.45
        y = m + (y - m) * (1 + dh * 0.35)
    # --- Clarity: midtone local contrast
    cl = st['clarity'] / 100.0 * g['cla']
    if cl:
        Ly = luma(np.clip(y, 0, 1))
        detail = Ly - blur(Ly, 0.008)
        wmid = 1 - np.abs(Ly - 0.5) * 2
        y = y + (cl * 0.9 * detail * np.clip(wmid, 0, 1))[..., None]
    y = np.clip(y, 0, 1)
    # --- Vibrance
    vib = st['vibrance'] / 100.0
    if vib:
        mx, mn = y.max(2), y.min(2)
        sat = (mx - mn) / (mx + 1e-6)
        gray = luma(y)[..., None]
        k = 1 + vib * (1 - sat)[..., None] * 0.9
        y = np.clip(gray + (y - gray) * k, 0, 1)
    # --- Keep neutral shadows neutral: in shade the camera WB leaves a faint blue in dark greys, which
    # vibrance then amplifies (blue ears/eyes on grey rhinos). Pull blue-leaning, low-saturation darks to neutral.
    Ly = luma(y)[..., None]
    blue_excess = np.clip(y[..., 2:3] - (y[..., 0:1] + y[..., 1:2]) / 2, 0, None)
    wdark = np.clip((0.55 - Ly) / 0.35, 0, 1)
    mx, mn = y.max(2, keepdims=True), y.min(2, keepdims=True)
    wlow = np.clip((0.65 - (mx - mn) / (mx + 1e-6)) / 0.25, 0, 1)
    y = np.clip(y - np.concatenate([-0.35 * blue_excess, -0.35 * blue_excess, 0.7 * blue_excess], 2) * wdark * wlow, 0, 1)
    # --- Residual look LUT (learned from his export)
    if lut is not None:
        lut = np.asarray(lut, dtype=np.float32)
        idx = np.linspace(0, 1, lut.shape[1])
        y = np.stack([np.interp(y[..., c], idx, lut[c]) for c in range(3)], -1)
    # --- Post-crop vignette (highlight priority-ish: darken edges, protect brights)
    va = st['vignette'] / 100.0 * g['vig']
    if va:
        h, w = y.shape[:2]
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
        fall = np.clip((r - 0.35) / 0.65, 0, 1) ** 2         # midpoint 50, feather 50
        mult = 1 + va * 0.85 * fall
        prot = 1 - 0.5 * luma(y)                              # highlight priority
        y = y * (1 - (1 - mult) * prot)[..., None]
    return np.clip(y, 0, 1)

def finish(y, st=STYLE):
    """Denoise + sharpen at full resolution, returns uint8."""
    u8 = (y * 255 + 0.5).astype(np.uint8)
    if st.get('denoise'):
        light = cv2.fastNlMeansDenoisingColored(u8, None, 1.5, 4, 5, 15)
        strong = cv2.GaussianBlur(light.astype(np.float32), (0, 0), 2.2)
        # detail mask: textured areas (fur, grass) keep the light pass; smooth bokeh gets the strong pass
        gray = cv2.cvtColor(light, cv2.COLOR_RGB2GRAY).astype(np.float32)
        det = cv2.GaussianBlur(np.abs(cv2.Laplacian(cv2.GaussianBlur(gray, (0, 0), 1.5), cv2.CV_32F)), (0, 0), 6)
        m = np.clip((det - 1.0) / 3.0, 0, 1)[..., None]
        mix = light.astype(np.float32) * m + strong * (1 - m)
        rng = np.random.default_rng(0)                     # fine dither in smooth areas -> no banding
        mix = mix + rng.normal(0, 0.9, mix.shape[:2])[..., None] * (1 - m)
        u8 = np.clip(mix + 0.5, 0, 255).astype(np.uint8)
    amt = st['sharpen'] / 100.0
    if amt:
        f = u8.astype(np.float32)
        b = cv2.GaussianBlur(f, (0, 0), st['sharpen_radius'])
        u8 = np.clip(f + (f - b) * amt * 1.2, 0, 255).astype(np.uint8)
    return u8

def preview_stats(path):
    """(p50, p95) luma of the camera's embedded JPEG preview - what the camera metered and how bright
    it let the highlights go."""
    import io
    with rawpy.imread(path) as raw:
        th = raw.extract_thumb()
    im = Image.open(io.BytesIO(th.data)).convert('L') if th.format == rawpy.ThumbFormat.JPEG else Image.fromarray(th.data).convert('L')
    a = np.asarray(im)
    return float(np.median(a)), float(np.percentile(a, 95))


def preview_median(path):
    return preview_stats(path)[0]


def auto_ev(lin_small, g, lut, cam_p50=None, cam_p95=None):
    """Exposure for the house look.

    Median target: ~12% brighter than the camera's rendering (his reference edit), but NO extra
    brightening for bright / high-key scenes (camera median >= 115), where it over-exposed sunlit
    rhinos. Hard highlight guard: the brightest 5% may not exceed the camera's own p95 (+3 levels,
    max 238) and clipped pixels stay under 0.3%. The guard wins over the median target - matching the
    median alone ran bright, hazy scenes to +2 EV and blew them out (Laikipia _U4A8533, _U4A8603)."""
    if cam_p50:
        target = cam_p50 * (1.12 if cam_p50 < 100 else 1.12 - 0.12 * min(1.0, (cam_p50 - 100) / 15.0))
    else:
        target = TARGET['p50']
    p95_cap = min(238.0, cam_p95 + 3.0) if cam_p95 else 238.0
    best, err, best_ok = 0.0, 1e9, None
    for ev in np.arange(-2.0, 3.01, 0.05):
        y = develop(lin_small, ev, g, lut=lut)
        L = luma(y) * 255
        ok = np.percentile(L, 95) <= p95_cap and (L >= 250).mean() <= 0.003
        e = abs(np.median(L) - target)
        if ok and e < err:
            best, err = ev, e
        if ok:
            best_ok = ev
    if err == 1e9:                      # nothing satisfied the guard (very bright frame): darkest tried
        best = -2.0
    return float(best)


ARTIST = os.environ.get('RTJ_ARTIST', 'Sanjeev Mishra')


def save(u8, out, src_exif_model='Canon EOS R3'):
    im = Image.fromarray(u8)
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    ex = im.getexif()
    ex[0x013B] = ARTIST                  # Artist
    ex[0x8298] = f'Copyright {ARTIST}'        # Copyright
    ex[0x010F] = 'Canon'; ex[0x0110] = src_exif_model
    ex[0x0131] = 'raw_to_jpeg v3 photo_develop.py'
    if out.lower().endswith('.png'):
        im.save(out, 'PNG', dpi=(300, 300), icc_profile=srgb)          # lossless intermediate for finishing/upscale
    else:
        im.save(out, 'JPEG', quality=97, subsampling=0, dpi=(300, 300), icc_profile=srgb, exif=ex)

def develop_file(inp, out, exposure=None, crop=None, half=False):
    """Develop one RAW to OUT (.png = lossless intermediate). crop = (x,y,w,h) fractions. Returns EV used."""
    cal = load_calib(); g = cal['gains']; lut = cal.get('lut')
    lin = render_linear(inp, half=half)
    if crop:
        fx, fy, fw, fh = crop
        H, W = lin.shape[:2]
        lin = lin[int(fy * H):int((fy + fh) * H), int(fx * W):int((fx + fw) * W)]
    small = cv2.resize(lin, (lin.shape[1] // 8, lin.shape[0] // 8), interpolation=cv2.INTER_AREA)
    p50, p95 = preview_stats(inp)
    ev = exposure if exposure is not None else auto_ev(small, g, lut, p50, p95)
    save(finish(develop(lin, ev, g, lut=lut)), out)
    return ev

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--exposure', type=float, default=None, help='override auto exposure (EV)')
    ap.add_argument('--half', action='store_true')
    ap.add_argument('--crop', type=str, default=None,
                    help='x,y,w,h as fractions of the 6000x4000 frame; applied BEFORE developing so the vignette frames the crop')
    a = ap.parse_args()
    cal = load_calib(); g = cal['gains']; lut = cal.get('lut')
    lin = render_linear(a.inp, half=a.half)
    if a.crop:
        fx, fy, fw, fh = [float(v) for v in a.crop.split(',')]
        H, W = lin.shape[:2]
        lin = lin[int(fy * H):int((fy + fh) * H), int(fx * W):int((fx + fw) * W)]
    small = cv2.resize(lin, (lin.shape[1] // 8, lin.shape[0] // 8), interpolation=cv2.INTER_AREA)
    p50, p95 = preview_stats(a.inp)
    ev = a.exposure if a.exposure is not None else auto_ev(small, g, lut, p50, p95)
    print(f'exposure EV {ev:+.2f}')
    y = develop(lin, ev, g, lut=lut)
    save(finish(y), a.out)
    print('saved', a.out)

if __name__ == '__main__':
    main()
