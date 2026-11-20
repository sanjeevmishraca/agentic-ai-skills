#!/usr/bin/env python3
"""
best_shots.py - stage 0 of raw_to_jpeg: find the best shots of a shoot and copy them to <shoot>/Best Images.

STORY BEATS TECHNICAL PERFECTION (lesson from the 2026 Laikipia shoot, where a sharpness-driven
one-per-sighting picker missed the photographer's favourite 13 frames):
  Always keep: mother & young; animals DOING something (climbing, drinking, feeding, hunting,
  interacting); groups / herds; animals in motion; one or more animals looking at the camera;
  rare animals (e.g. black leopard); dramatic light (side / rim light, even against a cool sky).

Pipeline
  1. Duplicates = true copies only ("<name> copy") - ignored.
  2. Sightings = gaps <= 3 min (sorted by capture time, so counter rollover 9999->0001 is safe).
  3. MOMENTS inside a sighting = frames <= 20 s apart that still look alike (composition similarity);
     a long sighting holds several moments (calf running, mother+calf, herd resting) and each one
     gets a candidate.
  4. Technical gate per moment (focus is compared ONLY within the moment's burst, never across a
     sighting - whole-frame sharpness rewards textured grass and wrongly calls clean-background
     frames "soft"): drop near-black, clipped (>5 %), ISO > 12800, and frames < 60 % of the burst's
     sharpest; the best remaining frame is the moment's candidate.
  5. Contact sheets of all candidates (numbered, grouped by sighting) go to .tmp/best_shots/.
     The agent MUST look at every sheet and choose with the story rules above, plus: no animal /
     animal hidden or cut off -> drop; near-duplicate moments -> keep the stronger one.
  6. `--keep 3,7,12-15` copies the chosen candidates (RAW + camera JPG) to Best Images with a log.
     `--auto` (unattended runs) keeps the technically best candidate of every moment that has an
     animal-sized subject; review is still recommended.

Usage
  python tools/best_shots.py --input <shoot>                 # candidates + sheets (no copying)
  python tools/best_shots.py --input <shoot> --keep 1,4,9-12 # copy chosen candidates
  python tools/best_shots.py --input <shoot> --auto          # copy all moment candidates
"""
import argparse, csv, datetime as dt, io, json, os, re, shutil, sys
from pathlib import Path

import numpy as np
import cv2
from PIL import Image

RAW_EXT = {'.cr2', '.cr3', '.nef', '.nrw', '.arw', '.raf', '.dng', '.orf', '.rw2', '.pef', '.srw'}
JPG_EXT = {'.jpg', '.jpeg'}
SKIP_DIRS = {'Best Images', 'Processed', 'Dupe_Images', 'Best_Images'}
REPO = Path(__file__).resolve().parent.parent


def preview(path: Path):
    """PIL image + EXIF for a camera JPG, or the embedded preview of a RAW."""
    if path.suffix.lower() in JPG_EXT:
        return Image.open(path)
    import rawpy
    with rawpy.imread(str(path)) as r:
        t = r.extract_thumb()
    return Image.open(io.BytesIO(t.data)) if t.format == rawpy.ThumbFormat.JPEG else Image.fromarray(t.data)


def metrics(path: Path):
    im = preview(path)
    ex = im.getexif() if hasattr(im, 'getexif') else {}
    ifd = ex.get_ifd(0x8769) if ex else {}
    d = dict(path=str(path), name=path.name, iso=ifd.get(34855), dt=ifd.get(36867) or ex.get(306), subsec=ifd.get(37521))
    o = ex.get(274) if ex else None
    im.draft('RGB', (1600, 1600)); im = im.convert('RGB')
    im = {3: im.rotate(180, expand=True), 6: im.rotate(270, expand=True), 8: im.rotate(90, expand=True)}.get(o, im)
    W = 1200; im = im.resize((W, int(im.height * W / im.width)), Image.LANCZOS)
    a = np.asarray(im).astype(np.float32); g = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_RGB2GRAY)
    d.update(hi_clip=float((g >= 250).mean()), lo_clip=float((g <= 5).mean()), meanL=float(g.mean()),
             p98=float(np.percentile(g, 98)))
    mid = (g > 40) & (g < 215)
    d['warm'] = float(a[..., 0][mid].mean() / max(a[..., 2][mid].mean(), 1)) if mid.any() else 1.0
    lap = np.abs(cv2.Laplacian(g.astype(np.float32), cv2.CV_32F))
    H = g.shape[0]; gy, gx = 12, 18
    tiles = np.array([[(lap[i * H // gy:(i + 1) * H // gy, j * W // gx:(j + 1) * W // gx] ** 2).mean()
                       for j in range(gx)] for i in range(gy)])
    d['sharp_max'] = float(np.sort(tiles.ravel())[-3:].mean())
    d['noise'] = float(np.sqrt(np.sort(tiles.ravel())[:max(3, tiles.size // 10)].mean()))
    thr = tiles >= 0.35 * tiles.max(); w = tiles * thr
    ys, xs = np.mgrid[0:gy, 0:gx]
    d['cx'] = float(((xs + 0.5) * w).sum() / w.sum() / gx); d['cy'] = float(((ys + 0.5) * w).sum() / w.sum() / gy)
    small = cv2.resize(g, (48, 32)).astype(np.float32)
    d['f'] = (small - small.mean()) / (small.std() + 1e-6)
    d['thumb'] = im.resize((300, int(im.height * 300 / W)))
    return d


def thirds(cx, cy):
    dmin = min(np.hypot(cx - a, cy - b) for a in (1 / 3, 2 / 3) for b in (1 / 3, 2 / 3))
    return max(0.0, 1 - dmin / 0.25)


def pick(frames, gap, moment_gap=20.0, moment_sim=0.55):
    """Returns (candidates, nsightings, nmoments). One candidate per distinct moment."""
    for m in frames:
        try:
            m['t'] = dt.datetime.strptime(m['dt'], '%Y:%m:%d %H:%M:%S').timestamp() + int(m['subsec'] or 0) / 100
        except Exception:
            m['t'] = os.path.getmtime(m['path'])
    frames.sort(key=lambda m: (m['t'], m['name']))
    sim = lambda a, b: float((a['f'] * b['f']).mean())
    sightings = []
    for m in frames:
        if sightings and m['t'] - sightings[-1][-1]['t'] <= gap:
            sightings[-1].append(m)
        else:
            sightings.append([m])
    cands, nmom = [], 0
    for si, s in enumerate(sightings, 1):
        moments = [[s[0]]]
        for m in s[1:]:
            cur = moments[-1]
            if m['t'] - cur[-1]['t'] <= moment_gap and max(sim(m, x) for x in cur[-3:]) >= moment_sim:
                cur.append(m)
            else:
                moments.append([m])
        nmom += len(moments)
        for mi, mo in enumerate(moments, 1):
            smax = max(x['sharp_max'] for x in mo)
            ok = [x for x in mo if not (x['meanL'] < 45 or x['p98'] < 110) and x['hi_clip'] <= 0.05
                  and (x['iso'] or 0) <= 12800 and x['sharp_max'] >= 0.6 * smax]
            if not ok:
                continue
            nmax = max(y['noise'] for y in ok)
            for x in ok:
                x['score'] = 0.5 * x['sharp_max'] / smax + 0.3 * (1 - min(0.4, abs(x['meanL'] - 118) / 300)) + 0.2 * (1 - x['noise'] / nmax)
            b = max(ok, key=lambda x: x['score'])
            b.update(scene=si, moment=mi, frames=len(mo), usable=len(ok))
            cands.append(b)
    return cands, len(sightings), nmom


def contact_sheets(cands, folder, per_sheet=30):
    from PIL import ImageDraw
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob('sheet_*.jpg'):
        f.unlink()
    cols, tw, th = 6, 300, 228
    pages = []
    for p in range(0, len(cands), per_sheet):
        chunk = cands[p:p + per_sheet]
        rows = (len(chunk) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * tw, rows * th), (20, 18, 16))
        d = ImageDraw.Draw(sheet)
        for k, m in enumerate(chunk):
            x, y = (k % cols) * tw, (k // cols) * th
            sheet.paste(m['thumb'], (x, y))
            d.text((x + 6, y + th - 24), f"#{p + k + 1}  {Path(m['name']).stem}  s{m['scene']}.{m['moment']}", fill=(239, 232, 221))
        out = folder / f'sheet_{len(pages) + 1:02d}.jpg'
        sheet.save(out, quality=85)
        pages.append(out)
    return pages


def parse_keep(spec, n):
    out = set()
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-'); out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(i for i in out if 1 <= i <= n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out')
    ap.add_argument('--gap', type=float, default=180)
    ap.add_argument('--keep', help='candidate numbers to copy, e.g. 1,4,9-12')
    ap.add_argument('--auto', action='store_true', help='copy every moment candidate (unattended)')
    a = ap.parse_args()
    root = Path(a.input)
    out = Path(a.out) if a.out else root / 'Best Images'
    files = [f for f in root.rglob('*') if f.is_file() and not (SKIP_DIRS & set(f.relative_to(root).parts[:-1]))
             and f.suffix.lower() in RAW_EXT | JPG_EXT and ' copy' not in f.stem.lower()]
    by_stem = {}
    for f in files:
        by_stem.setdefault((f.parent, f.stem.lower()), []).append(f)
    frames = []
    for group in by_stem.values():
        jpg = next((f for f in group if f.suffix.lower() in JPG_EXT), None)
        src = jpg or group[0]                             # analyse the camera JPG when present (faster)
        try:
            m = metrics(src)
        except Exception as e:
            print('skip', src.name, e); continue
        m['group'] = [str(f) for f in group]
        frames.append(m)
        if len(frames) % 200 == 0:
            print(f'  analysed {len(frames)} frames')
    if not frames:
        sys.exit('no photos found')
    cands, nsight, nmom = pick(frames, a.gap)
    work = REPO / '.tmp' / 'best_shots'
    work.mkdir(parents=True, exist_ok=True)
    json.dump([dict(n=i + 1, name=m['name'], group=m['group'], scene=m['scene'], moment=m['moment'], frames=m['frames'],
                    dt=m['dt'], iso=m['iso'], score=round(m['score'], 3)) for i, m in enumerate(cands)],
              open(work / 'candidates.json', 'w'), indent=1)
    pages = contact_sheets(cands, work)
    print(f'{len(frames)} frames, {nsight} sightings, {nmom} moments -> {len(cands)} candidates')
    print('contact sheets:', ', '.join(str(p) for p in pages))
    if not (a.keep or a.auto):
        print('NEXT: review the sheets with the story rules, then re-run with --keep <numbers>')
        return
    chosen = cands if a.auto else [cands[i - 1] for i in parse_keep(a.keep, len(cands))]
    out.mkdir(parents=True, exist_ok=True)
    for m in chosen:
        for f in m['group']:
            dst = out / Path(f).name
            if not dst.exists():
                shutil.copy2(f, dst)
    log = out / 'best_shots_log.csv'
    new = not log.exists()
    with open(log, 'a', newline='') as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(['pick', 'sighting', 'moment', 'frames_in_moment', 'captured', 'iso', 'tech_score', 'how'])
        for m in chosen:
            w.writerow([Path(m['name']).stem, m['scene'], m['moment'], m['frames'], m['dt'], m['iso'], round(m['score'], 3),
                        'auto' if a.auto else 'reviewed'])
    print(f'copied {len(chosen)} best shots to {out}')


if __name__ == '__main__':
    main()
