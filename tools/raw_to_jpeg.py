#!/usr/bin/env python3
"""
raw_to_jpeg.py - WAT Framework Tool - RAW -> finished, print-ready JPEG
Version 3.0.0 "final" - 2026-11-20 10:22 PST

Full pipeline (each stage is its own tool in tools/, all intermediates lossless PNG):

  1. DEVELOP   photo_develop.py   house look learned from the photographer's own Camera Raw edit
               (ACR PV15.4 Adobe Color: Contrast +34, Highlights -87, Shadows +76, Whites +9,
               Blacks -34, Clarity +24, Dehaze +23, Vibrance +15, Sharpen 40, AI-style denoise,
               vignette -37 highlight-priority), calibrated gains + residual look LUT (calib.json).
               Auto exposure = median ~12% brighter than the camera's own preview.
               Optional crop (applied before developing, so the vignette frames the crop).
  2. FINISH    expert_finish.py   GrabCut subject mask; calmer/darker background, subject dodge,
               local WB for shaded fur, face clarity + eye lift, neutral dark markings.
  3. UPSCALE   upscale_print.py   largest useful print size = 3x: defringe, Lanczos in 2x steps,
               luminance-only detail-masked USM (r2.0 scaled / 90% / t2); 300 ppi.
  4. SIGN      sign_image.py      signature bottom-right on copies in Processed/signed/.

Outputs per RAW, in <output> (default <input>/Processed):
  <name>_expert.jpg           finished image, JPEG q97 4:4:4, sRGB, 300 ppi
  <name>_expert_print3x.jpg   print master, JPEG q100 4:4:4, sRGB, 300 ppi
  signed/<same names>         signed copies (if signature PNGs are available)

Usage
  python tools/raw_to_jpeg.py --input <folder|file|zip> [--output DIR] [--plan plan.json]
                              [--exposure EV] [--crop x,y,w,h] [--subject x,y,w,h] [--face x,y]
                              [--factor 3] [--no-finish] [--no-upscale] [--no-sign] [--sig-dir DIR]

  --plan    JSON mapping RAW file name (or stem) -> per-image options, e.g.
            {"_U4A0059": {"exposure": 1.25, "crop": [0.2282, 0.3888, 0.6822, 0.5382],
                          "subject": [0.2, 0.05, 0.35, 0.9], "face": [0.386, 0.225]}}
            crop is in fractions of the full frame; subject/face in fractions of the CROPPED frame.
            Options on the command line apply to every image unless the plan overrides them.

Exit codes: 0 success | 1 bad args | 2 no RAW files | 4 partial failures
"""
import argparse, json, os, sys, tempfile, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import photo_develop, expert_finish, upscale_print, sign_image  # noqa: E402

VERSION = "3.0.0"
RELEASED = "2026-11-20 10:22 PST"
RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.nrw', '.arw', '.raf', '.dng', '.orf', '.rw2',
                  '.pef', '.srw', '.3fr', '.mef', '.mrw', '.rwl', '.x3f', '.erf'}
REPO = HERE.parent
TMP = REPO / '.tmp'


def collect(inp):
    p = Path(inp)
    if p.is_file() and p.suffix.lower() == '.zip':
        dest = TMP / ('unzip_' + p.stem)
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(p) as z:
            z.extractall(dest)
        p = dest
    if p.is_file():
        return [p] if p.suffix.lower() in RAW_EXTENSIONS else []
    return sorted(f for f in p.rglob('*') if f.suffix.lower() in RAW_EXTENSIONS and 'Processed' not in f.parts)


def nums(v, n):
    if v is None:
        return None
    if isinstance(v, str):
        v = [float(t) for t in v.split(',')]
    v = tuple(float(t) for t in v)
    if len(v) != n:
        raise ValueError(f'expected {n} numbers, got {v}')
    return v


def process(raw, out_dir, o, sig_dir, log):
    stem = raw.stem
    with tempfile.TemporaryDirectory(dir=TMP) as td:
        dev = Path(td) / f'{stem}_dev.png'
        fin = Path(td) / f'{stem}_expert.png'
        ev = photo_develop.develop_file(str(raw), str(dev), o.get('exposure'), nums(o.get('crop'), 4))
        log(f'  developed  EV {ev:+.2f}')
        if o.get('finish', True):
            expert_finish.run(str(dev), str(fin), nums(o.get('subject'), 4), nums(o.get('face'), 2))
            log('  expert finish done')
        else:
            fin = dev
        std = out_dir / f'{stem}_expert.jpg'
        from PIL import Image
        im = Image.open(fin)
        info = {k: im.info[k] for k in ('icc_profile', 'dpi') if k in im.info}
        im.convert('RGB').save(std, 'JPEG', quality=97, subsampling=0, **info)
        outs = [std]
        if o.get('upscale', True):
            pr = out_dir / f'{stem}_expert_print3x.jpg'
            w, h = upscale_print.upscale(str(fin), str(pr), float(o.get('factor', 3.0)))
            log(f'  print master {w}x{h} ({w/300:.1f} x {h/300:.1f} in @300 ppi)')
            outs.append(pr)
    signed = []
    if o.get('sign', True) and sig_dir:
        for f in outs:
            signed.append(sign_image.sign(f, out_dir / 'signed', sign_image.Opts))
    return dict(raw=str(raw), ev=ev, outputs=[str(p) for p in outs], signed=[str(p) for p in signed])


def main():
    ap = argparse.ArgumentParser(description=f'raw_to_jpeg v{VERSION} ({RELEASED})')
    ap.add_argument('--input', required=True)
    ap.add_argument('--output')
    ap.add_argument('--plan')
    ap.add_argument('--exposure', type=float)
    ap.add_argument('--crop'); ap.add_argument('--subject'); ap.add_argument('--face')
    ap.add_argument('--factor', type=float, default=3.0)
    ap.add_argument('--no-finish', action='store_true')
    ap.add_argument('--no-upscale', action='store_true')
    ap.add_argument('--no-sign', action='store_true')
    ap.add_argument('--sig-dir')
    ap.add_argument('--version', action='version', version=f'raw_to_jpeg {VERSION} ({RELEASED})')
    a = ap.parse_args()

    TMP.mkdir(exist_ok=True)
    raws = collect(a.input)
    if not raws:
        print('No RAW files found. Supported: ' + ', '.join(sorted(RAW_EXTENSIONS)))
        sys.exit(2)
    base = Path(a.input) if Path(a.input).is_dir() else Path(a.input).parent
    out_dir = Path(a.output) if a.output else base / 'Processed'
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = json.load(open(a.plan)) if a.plan else {}

    sig_dir = None
    if not a.no_sign:
        sig_dir = sign_image.find_sig_dir(a.sig_dir)
        if sig_dir:
            sign_image.load_signatures(sig_dir)
        else:
            print('note: signature PNGs not found (--sig-dir / RTJ_SIGNATURE_DIR) - skipping signing')

    defaults = dict(exposure=a.exposure, crop=a.crop, subject=a.subject, face=a.face, factor=a.factor,
                    finish=not a.no_finish, upscale=not a.no_upscale, sign=not a.no_sign)
    logf = open(TMP / 'raw_processing.log', 'a')
    def log(msg):
        print(msg); logf.write(msg + '\n'); logf.flush()

    log(f'raw_to_jpeg v{VERSION}  {time.strftime("%Y-%m-%d %H:%M:%S")}  {len(raws)} file(s) -> {out_dir}')
    results = dict(version=VERSION, processed=[], failed=[])
    for raw in raws:
        o = dict(defaults)
        o.update({k: v for k, v in (plan.get(raw.name) or plan.get(raw.stem) or {}).items()})
        log(f'{raw.name}')
        try:
            results['processed'].append(process(raw, out_dir, o, sig_dir, log))
        except Exception as e:  # keep going, report at the end
            log(f'  FAILED: {e}')
            results['failed'].append(dict(raw=str(raw), error=str(e)))
    json.dump(results, open(TMP / 'raw_processing_results.json', 'w'), indent=2)
    log(f'done: {len(results["processed"])} ok, {len(results["failed"])} failed')
    sys.exit(4 if results['failed'] else 0)


if __name__ == '__main__':
    main()
