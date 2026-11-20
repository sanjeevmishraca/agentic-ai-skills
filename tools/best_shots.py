#!/usr/bin/env python3
"""
best_shots.py - stage 0 of raw_to_jpeg: pick ONE best frame per sighting and copy it to <shoot>/Best Images.

Rules (approved on the 2026 Laikipia shoot):
  * Duplicates = true copies only ("<name> copy", same capture time) - never picked.
  * Sighting = consecutive frames with gaps <= 3 minutes (sorted by capture time, so the camera
    counter rolling over 9999 -> 0001 doesn't split or merge sightings).
  * Hard rejects: underexposed / near-black, clipped highlights (>5 %), ISO > 12800, soft
    (< 60 % of the sighting's sharpest frame).
  * Score the rest: sharpness 30 %, exposure 20 %, noise 10 %, rule of thirds 15 %,
    lead room in the direction of motion 15 %, golden light by image WARMTH (not the clock) 10 %.
  * Copy RAW + camera JPG of each pick (originals untouched) and write best_shots_log.csv.
  * A contact sheet is written to .tmp/best_shots_review.jpg - the agent MUST look at it and drop
    frames with no animal (tents, empty scenes) or an animal hidden/cut off before processing.

Usage: python tools/best_shots.py --input <shoot folder> [--out "<shoot>/Best Images"] [--gap 180]
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
    d['thumb'] = im.resize((300, int(im.height * 300 / W)))
    return d


def thirds(cx, cy):
    dmin = min(np.hypot(cx - a, cy - b) for a in (1 / 3, 2 / 3) for b in (1 / 3, 2 / 3))
    return max(0.0, 1 - dmin / 0.25)


def pick(frames, gap):
    for m in frames:
        try:
            m['t'] = dt.datetime.strptime(m['dt'], '%Y:%m:%d %H:%M:%S').timestamp() + int(m['subsec'] or 0) / 100
        except Exception:
            m['t'] = os.path.getmtime(m['path'])
    frames.sort(key=lambda m: (m['t'], m['name']))
    scenes = []
    for m in frames:
        if scenes and m['t'] - scenes[-1][-1]['t'] <= gap:
            scenes[-1].append(m)
        else:
            scenes.append([m])
    picks, rejected = [], []
    for i, s in enumerate(scenes, 1):
        smax = max(m['sharp_max'] for m in s)
        ok = []
        for m in s:
            why = []
            if m['meanL'] < 45 or m['p98'] < 110: why.append('underexposed')
            if m['hi_clip'] > 0.05: why.append('highlights clipped')
            if (m['iso'] or 0) > 12800: why.append('ISO too high')
            if m['sharp_max'] < 0.6 * smax: why.append('soft')
            m['why'] = why
            if not why: ok.append(m)
        if not ok:
            rejected.append((i, len(s), s[0]['name'], sorted({w for m in s for w in m['why']}))); continue
        cx = np.array([m['cx'] for m in s]); n = len(s)
        slope = np.polyfit(np.arange(n), cx, 1)[0] if n > 2 else 0
        move = 'right' if slope * n > 0.08 else 'left' if slope * n < -0.08 else 'static'
        nmin = min(m['noise'] for m in ok); smx = max(m['sharp_max'] for m in ok)
        for m in ok:
            ex = 1 - min(0.4, abs(m['meanL'] - 118) / 300) - (0.2 if m['hi_clip'] > 0.02 else 0) - (0.2 if m['lo_clip'] > 0.15 else 0)
            lead = min(1, {'right': 1 - m['cx'], 'left': m['cx'], 'static': 0.5}[move] / 0.6)
            gold = min(1.0, max(0.0, (m['warm'] - 1.05) / 0.25))
            m['score'] = 0.30 * m['sharp_max'] / smx + 0.20 * ex + 0.10 * nmin / m['noise'] + 0.15 * thirds(m['cx'], m['cy']) + 0.15 * lead + 0.10 * gold
            m.update(move=move, lead=lead, gold=gold)
        b = max(ok, key=lambda m: m['score'])
        b.update(scene=i, frames=n, usable=len(ok))
        picks.append(b)
    return picks, rejected, len(scenes)


def contact_sheet(picks, out):
    cols, tw, th = 6, 300, 230
    rows = (len(picks) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * tw, rows * th), (20, 18, 16))
    from PIL import ImageDraw
    d = ImageDraw.Draw(sheet)
    for k, m in enumerate(picks):
        x, y = (k % cols) * tw, (k // cols) * th
        sheet.paste(m['thumb'], (x, y))
        d.text((x + 6, y + th - 26), f"{k + 1}. {Path(m['name']).stem}  s{m['scene']}", fill=(239, 232, 221))
    sheet.save(out, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--out')
    ap.add_argument('--gap', type=float, default=180)
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
    picks, rejected, nscenes = pick(frames, a.gap)
    out.mkdir(parents=True, exist_ok=True)
    for m in picks:
        for f in m['group']:
            dst = out / Path(f).name
            if not dst.exists():
                shutil.copy2(f, dst)
    with open(out / 'best_shots_log.csv', 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['pick', 'sighting', 'frames_in_sighting', 'usable', 'captured', 'iso', 'motion', 'golden', 'score'])
        for m in picks:
            w.writerow([Path(m['name']).stem, m['scene'], m['frames'], m['usable'], m['dt'], m['iso'], m['move'],
                        round(m['gold'], 2), round(m['score'], 3)])
    (REPO / '.tmp').mkdir(exist_ok=True)
    contact_sheet(picks, REPO / '.tmp' / 'best_shots_review.jpg')
    print(f'{len(frames)} frames, {nscenes} sightings -> {len(picks)} best shots in {out}')
    if rejected:
        print('sightings with no usable frame:', rejected)
    print('REVIEW: .tmp/best_shots_review.jpg - remove frames with no animal before processing')


if __name__ == '__main__':
    main()
