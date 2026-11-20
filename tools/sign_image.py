#!/usr/bin/env python3
"""Stamp the photographer's signature in the bottom-right corner (stage 4 of raw_to_jpeg v3).

Signature PNGs (transparent): SM_signature_black.png / SM_signature_white.png in the folder given by
--sig-dir, $RTJ_SIGNATURE_DIR, or ./signature next to the repo root. They are NOT committed to the
public repo (a handwritten signature should not be published) - keep them locally.
Defaults: 5.25% of long edge wide, 1% inset, 85% opacity, auto black/white by corner brightness.
"""
import os, sys, argparse
from pathlib import Path
from PIL import Image, ImageStat

HERE = Path(__file__).resolve().parent
SIG = {}

def find_sig_dir(explicit=None):
    for d in (explicit, os.environ.get("RTJ_SIGNATURE_DIR"), HERE.parent / "signature", HERE):
        if d and (Path(d) / "SM_signature_black.png").exists():
            return Path(d)
    return None

def load_signatures(sig_dir):
    for c in ("black", "white"):
        SIG[c] = Image.open(Path(sig_dir) / f"SM_signature_{c}.png").convert("RGBA")

class Opts:
    width, margin, opacity, color = 0.0525, 0.01, 0.85, "auto"
EXTS = {".jpg", ".jpeg", ".tif", ".tiff", ".png"}

def sign(src: Path, out_dir: Path, a):
    im = Image.open(src)
    info = {k: im.info[k] for k in ("icc_profile", "exif", "dpi") if k in im.info}
    mode = im.mode
    base = im.convert("RGBA") if mode != "RGBA" else im.copy()
    W, H = base.size; L = max(W, H)
    sw = int(L * a.width); s0 = SIG["black"]
    sh = int(s0.height * sw / s0.width); m = int(L * a.margin)
    x, y = W - sw - m, H - sh - m
    color = a.color
    if color == "auto":
        lum = ImageStat.Stat(base.crop((x, y, x + sw, y + sh)).convert("L")).mean[0]
        color = "white" if lum < 128 else "black"
    sig = SIG[color].resize((sw, sh), Image.LANCZOS)
    if a.opacity < 1:
        al = sig.getchannel("A").point(lambda v: int(v * a.opacity)); sig.putalpha(al)
    base.alpha_composite(sig, (x, y))
    out = base if mode == "RGBA" else base.convert("RGB" if mode not in ("L", "I;16") else "L")
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / src.name
    kw = dict(info)
    if src.suffix.lower() in (".jpg", ".jpeg"): kw.update(quality=100, subsampling=0)
    if src.suffix.lower() in (".tif", ".tiff"): kw.update(compression="tiff_lzw")
    out.save(dst, **kw)
    print(f"signed ({color}): {dst}")
    return dst

def main():
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="+"); p.add_argument("--out")
    p.add_argument("--width", type=float, default=0.0525); p.add_argument("--margin", type=float, default=0.01)
    p.add_argument("--opacity", type=float, default=0.85); p.add_argument("--color", default="auto", choices=["auto", "black", "white"])
    p.add_argument("--sig-dir")
    a = p.parse_args()
    d = find_sig_dir(a.sig_dir)
    if not d:
        sys.exit("signature PNGs not found: pass --sig-dir or set RTJ_SIGNATURE_DIR")
    load_signatures(d)
    for raw in a.paths:
        P = Path(raw)
        files = [f for f in P.iterdir() if f.suffix.lower() in EXTS] if P.is_dir() else [P]
        for f in sorted(files):
            sign(f, Path(a.out) if a.out else f.parent / "signed", a)

if __name__ == "__main__":
    main()
