#!/usr/bin/env python3
"""
raw_to_jpeg.py - WAT Framework Tool - RAW -> finished, print-ready JPEG
Version 3.1.0 - 2026-11-20 12:40 PST (3.0.0 "final" + Best Images / Processed folder structure)

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
  3b. TONE     print_tone.py      real blacks, mid-tones <= 128, highlight roll-off (sunlit animals were
               coming out white/milky); plan "tone": false to skip, "warm": 0.04 for golden scenes.
  4. SIGN      sign_image.py      signature bottom-right on copies in Processed/signed/.

Folder layout (default):
  <shoot folder>/              your originals (never modified)
  <shoot folder>/Best Images/  stage 0 picks the best frame of each moment, story first (RAW + camera JPG) - best_shots.py
  <shoot folder>/Processed/    finished JPEGs of everything in Best Images (+ signed/)
  --skip-pick processes an existing Best Images folder (e.g. after you reviewed/edited the picks);
  --all processes every RAW in the shoot without picking.

Outputs per RAW, in <output> (default <shoot folder>/Processed):
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

Delivery gate (3.4.0): output defaults to a NEW dated folder <shoot>/Processed/<date> final and a
non-empty output folder is refused (exit 5) unless --allow-existing. After processing, verify_delivery
writes delivery_manifest.json and checks the folder holds exactly the produced files (exit 6 if not).
Re-run `verify_delivery.py check` against the folder the user looks at before reporting done.

Exit codes: 0 success+verified | 1 bad args | 2 no RAW files | 4 partial failures | 5 output not empty
            | 6 delivery verification failed
"""
import argparse, json, os, sys, tempfile, time, zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import photo_develop, expert_finish, upscale_print, sign_image  # noqa: E402
import verify_delivery, print_tone  # noqa: E402
import best_shots  # noqa: E402

VERSION = "3.6.0"
RELEASED = "2026-11-23 16:00 PST"
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
    return sorted(f for f in p.rglob('*') if f.suffix.lower() in RAW_EXTENSIONS
                  and not ({'Processed', 'Best Images', 'Dupe_Images'} & set(f.relative_to(p).parts[:-1])))


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
        import numpy as np
        im = Image.open(fin)
        info = {k: im.info[k] for k in ('icc_profile', 'dpi') if k in im.info}
        if o.get('tone', True) or o.get('warm') or o.get('golden'):
            # print tone: real blacks, mid-tones <= 128, highlight roll-off, optional warmth
            arr = np.asarray(im.convert('RGB')).astype(np.float32) / 255
            rep = []
            if o.get('tone', True):
                arr = print_tone.tone(arr, warm=float(o.get('warm') or 0), report=rep)
            else:
                arr = print_tone.tone(arr, mid_max=1.0, black=1.0, warm=float(o['warm']), report=rep, shoulder=False)
            if o.get('golden'):
                arr = print_tone.golden(arr, float(o['golden']))
                rep[0] += f', golden {float(o["golden"]):.1f}'
            log(f'  print tone: {rep[0]}')
            im = Image.fromarray((arr * 255 + 0.5).astype(np.uint8))
            im.save(fin)                     # the print master is built from the toned image too
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
    ap.add_argument('--skip-pick', action='store_true', help='process the existing <input>/Best Images folder')
    ap.add_argument('--all', action='store_true', help='process every RAW, no best-shot picking')
    ap.add_argument('--allow-existing', action='store_true',
                    help='allow writing into a non-empty output folder (default: refuse - every delivery '
                         'goes into a new, empty folder so stale files from earlier runs cannot mix in)')
    ap.add_argument('--version', action='version', version=f'raw_to_jpeg {VERSION} ({RELEASED})')
    a = ap.parse_args()

    TMP.mkdir(exist_ok=True)
    base = Path(a.input) if Path(a.input).is_dir() else Path(a.input).parent
    best = base / 'Best Images'
    if Path(a.input).is_dir() and not a.all:
        if not a.skip_pick:
            print('stage 0: picking best shots ->', best)
            sys.argv = ['best_shots.py', '--input', str(base), '--out', str(best), '--auto']
            best_shots.main()
        raws = collect(best)
    else:
        raws = collect(a.input)
    if not raws:
        print('No RAW files found. Supported: ' + ', '.join(sorted(RAW_EXTENSIONS)))
        sys.exit(2)
    if a.output:
        out_dir = Path(a.output)
    else:  # fresh, dated delivery folder: <shoot>/Processed/<YYYY-MM-DD> final[ 2, 3 ...]
        root = base / 'Processed' / f'{time.strftime("%Y-%m-%d")} final'
        out_dir, k = root, 2
        while out_dir.exists() and any(out_dir.iterdir()):
            out_dir, k = root.with_name(f'{root.name} {k}'), k + 1
    if out_dir.exists() and any(out_dir.iterdir()) and not a.allow_existing:
        print(f'REFUSED: output folder is not empty: {out_dir}\n'
              f'  Every delivery goes into a new, empty folder so files from earlier runs cannot mix in.\n'
              f'  Pick a new --output, or pass --allow-existing if you really mean to add to it.')
        sys.exit(5)
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
    if results['failed']:
        log('delivery NOT verified: fix the failures first')
        sys.exit(4)
    # Delivery gate: record exactly what was produced, then verify the folder holds only that.
    approved = ','.join(Path(r['raw']).stem for r in results['processed'])
    for argv in (['manifest', str(out_dir), '--approved', approved],
                 ['check', '--manifest', str(out_dir / verify_delivery.MANIFEST_NAME), '--dir', str(out_dir)]):
        sys.argv = ['verify_delivery.py'] + argv
        try:
            verify_delivery.main()
        except SystemExit as e:
            if e.code:
                log('delivery verification FAILED - do not hand this folder over')
                sys.exit(6)
    log(f'delivery verified: {out_dir}')
    sys.exit(0)


if __name__ == '__main__':
    main()
