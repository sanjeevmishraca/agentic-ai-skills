"""Separate a subject from a busy background: GrabCut subject mask (seeded by a box + a sure-subject
ellipse), then blur and slightly subdue everything else with a feathered falloff, and tighten the crop."""
import sys, numpy as np, cv2
from PIL import Image

def separate(img, box, core, blur=7.0, subdue=0.88, feather=14):
    H, W = img.shape[:2]
    s = 900.0 / W
    small = cv2.resize(img, (int(W * s), int(H * s)), interpolation=cv2.INTER_AREA)
    h, w = small.shape[:2]
    m = np.full((h, w), cv2.GC_BGD, np.uint8)
    bx, by, bw, bh = box
    m[int(by*h):int((by+bh)*h), int(bx*w):int((bx+bw)*w)] = cv2.GC_PR_FGD
    for (cx, cy, rx, ry) in core:
        cv2.ellipse(m, (int(cx*w), int(cy*h)), (int(rx*w), int(ry*h)), 0, 0, 360, cv2.GC_FGD, -1)
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), m, None, bgd, fgd, 8, cv2.GC_INIT_WITH_MASK)
    fg = np.where((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg)
    if n > 1:
        fg = np.where(lab == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA])), 255, 0).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    fg = cv2.resize(fg, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255
    a = np.clip(cv2.GaussianBlur(fg, (0, 0), feather * W / 2500), 0, 1)[..., None]
    f = img.astype(np.float32)
    # lens-like falloff: blur grows with distance from the subject (near branches only slightly soft)
    dist = cv2.distanceTransform((fg < 0.5).astype(np.uint8), cv2.DIST_L2, 5) / W
    t = np.clip(dist / 0.18, 0, 1)[..., None]                  # 0 at the subject edge -> 1 at 18% of width away
    b1 = cv2.GaussianBlur(f, (0, 0), 1.5 * W / 2500)
    b2 = cv2.GaussianBlur(f, (0, 0), blur * W / 2500)
    bg = b1 * (1 - t) + b2 * t
    g = bg.mean(2, keepdims=True)
    k = subdue + (1 - subdue) * (1 - t)                        # darker / calmer further out
    bg = (g + (bg - g) * (0.92 - 0.1 * t)) * k
    out = f * a + bg * (1 - a)
    return np.clip(out, 0, 255).astype(np.uint8), fg

if __name__ == '__main__':
    import argparse, json
    ap = argparse.ArgumentParser(description='Blur/subdue the background behind a subject, then crop.')
    ap.add_argument('inp'); ap.add_argument('out')
    ap.add_argument('--box', required=True, help='x,y,w,h fractions around the subject')
    ap.add_argument('--core', default='[]', help='JSON list of sure-subject ellipses [cx,cy,rx,ry] (fractions)')
    ap.add_argument('--crop', help='x0,y0,x1 fractions; height follows 3:2')
    ap.add_argument('--blur', type=float, default=7.0)
    a = ap.parse_args()
    pil = Image.open(a.inp); info = {k: pil.info[k] for k in ('icc_profile', 'exif', 'dpi') if k in pil.info}
    img = np.asarray(pil.convert('RGB'))
    out, fg = separate(img, tuple(float(v) for v in a.box.split(',')), json.loads(a.core), blur=a.blur)
    H, W = out.shape[:2]
    if a.crop:
        fx0, fy0, fx1 = (float(v) for v in a.crop.split(','))
        x0, x1 = int(fx0 * W), int(fx1 * W); ch = int((x1 - x0) / 1.5); y0 = int(fy0 * H); y1 = min(H, y0 + ch)
        out = out[y0:y1, x0:x1]
    Image.fromarray(out).save(a.out, 'JPEG', quality=97, subsampling=0, **info)
    print('saved', a.out, out.shape)
