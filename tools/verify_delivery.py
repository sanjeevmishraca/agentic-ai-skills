#!/usr/bin/env python3
"""
verify_delivery.py - WAT Framework Tool - delivery gate for finished photos
Version 1.0.0 - 2026-11-23

Why this exists: a delivery folder once still held rejected images from an earlier run
(8533, 8603, ...) while the work was reported as done. This tool makes that impossible to miss:
a delivery is only "done" when the folder the customer/photographer looks at contains EXACTLY
the approved files - nothing extra, nothing missing, every size matching what was reviewed.

Two steps:

  1. manifest  - after the finals are reviewed, record exactly what is approved:
       python tools/verify_delivery.py manifest <delivery_dir> [--approved 0010,0059,...]
                                                [--allow-extra NAME ...]
     Writes <delivery_dir>/delivery_manifest.json with name, size and sha256 of every file in
     <delivery_dir> and its signed/ subfolder. --approved (stems or 4-digit numbers) makes the
     manifest step itself fail if an approved image is missing or an unapproved one is present.
     --allow-extra names files that are not ours but may sit in the root (e.g. the photographer's
     own edit); they are reported, never silently ignored.

  2. check     - compare a target folder against the manifest:
       python tools/verify_delivery.py check --manifest M.json --dir <target_dir>
       python tools/verify_delivery.py check --manifest M.json \
             --listing .=root_listing.json --listing signed=signed_listing.json
     --dir   : a local folder (the pipeline runs this on the machine that holds the files).
     --listing SUB=FILE : JSON from a remote directory listing (e.g. the device bridge's
               device_list_dir), for when the folder is on another machine. Every folder in the
               manifest must be given a listing.
     Prints a PASS/FAIL report and the exact file list. Exit 0 = PASS, 3 = FAIL.

Rule for the agent: never report a delivery as done unless `check` printed PASS against the
folder the user actually looks at, and paste that report into the handover.
"""
import argparse, hashlib, json, re, sys, time
from pathlib import Path

VERSION = '1.0.0'
MANIFEST_NAME = 'delivery_manifest.json'
DELIVERY_FOLDERS = {'.', 'signed'}   # root = unsigned masters, signed/ = signed copies
SKIP = {MANIFEST_NAME, 'desktop.ini', 'Thumbs.db', '.DS_Store'}


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def stem_id(name):
    """'_U4A8533_expert.jpg' -> '8533'; falls back to the stem without _expert."""
    m = re.search(r'(\d{4})(?!.*\d{4})', Path(name).stem)
    return m.group(1) if m else Path(name).stem.replace('_expert', '')


def scan_local(d):
    """{subfolder: {name: size}} for d and every subfolder (one level: signed/, etc.), plus dirs."""
    d = Path(d)
    out, dirs = {'.': {}}, {'.': []}
    for p in sorted(d.iterdir()):
        if p.name in SKIP:
            continue
        if p.is_file():
            out['.'][p.name] = p.stat().st_size
        elif p.is_dir():
            dirs['.'].append(p.name)
            out[p.name], dirs[p.name] = {}, []
            for q in sorted(p.iterdir()):
                if q.name in SKIP:
                    continue
                if q.is_file():
                    out[p.name][q.name] = q.stat().st_size
                else:
                    dirs[p.name].append(q.name)
    return out, dirs


def scan_listing(pairs):
    out, dirs = {}, {}
    for pair in pairs:
        sub, _, f = pair.partition('=')
        data = json.load(open(f))
        entries = data['entries'] if isinstance(data, dict) else data
        if isinstance(data, dict) and data.get('truncated'):
            raise SystemExit(f'listing {f} is truncated - cannot verify')
        out[sub], dirs[sub] = {}, []
        for e in entries:
            if e['name'] in SKIP or e.get('depth'):
                continue
            if e.get('type') == 'file':
                out[sub][e['name']] = e.get('size')
            elif e.get('type') == 'dir':
                dirs[sub].append(e['name'])
    return out, dirs


def cmd_manifest(a):
    d = Path(a.delivery_dir)
    files, dirs = scan_local(d)
    allow = set(a.allow_extra or [])
    man = dict(tool=f'verify_delivery {VERSION}', created=time.strftime('%Y-%m-%d %H:%M:%S'),
               delivery_dir=str(d.resolve()), allowed_extra=sorted(allow), folders={})
    problems = []
    for sub, names in files.items():
        man['folders'][sub] = {}
        for n, size in names.items():
            p = d / n if sub == '.' else d / sub / n
            man['folders'][sub][n] = dict(size=size, sha256=sha256(p))
    if a.approved:
        want = {stem_id(t.strip()) for t in a.approved.split(',') if t.strip()}
        for sub, names in man['folders'].items():
            if sub not in DELIVERY_FOLDERS:
                problems.append(f'unexpected folder {sub}/ ({len(names)} files) - move it out')
                continue
            got = {stem_id(n) for n in names if n not in allow}
            for m in sorted(want - got):
                problems.append(f'{sub}: approved {m} is MISSING')
            for x in sorted(got - want):
                problems.append(f'{sub}: {x} is NOT approved')
        man['approved'] = sorted(want)
    for sub, ds in dirs.items():
        for x in ds:
            if sub != '.' or x not in man['folders']:
                problems.append(f'unexpected folder {sub}/{x}/ - move it out')
    if problems:
        print('MANIFEST REFUSED - the delivery folder does not match the approved list:')
        for p in problems:
            print('  -', p)
        sys.exit(3)
    (d / MANIFEST_NAME).write_text(json.dumps(man, indent=2))
    n = sum(len(v) for v in man['folders'].values())
    print(f'manifest written: {d / MANIFEST_NAME}  ({n} files in {len(man["folders"])} folder(s))')


def compare(man, files, dirs):
    allow = set(man.get('allowed_extra', []))
    lines, ok = [], True
    for sub, expected in man['folders'].items():
        if sub not in files:
            lines.append(f'FAIL  {sub}/: no listing / folder missing')
            ok = False
            continue
        got = files[sub]
        extra = sorted(set(got) - set(expected) - (allow if sub == '.' else set()))
        missing = sorted(set(expected) - set(got))
        wrong = sorted(n for n in set(expected) & set(got)
                       if got[n] is not None and got[n] != expected[n]['size'])
        mine = [n for n in got if n in expected]
        status = 'PASS' if not (extra or missing or wrong) else 'FAIL'
        ok &= status == 'PASS'
        lines.append(f'{status}  {sub}/  {len(mine)}/{len(expected)} approved files present, '
                     f'{len(extra)} extra, {len(missing)} missing, {len(wrong)} size mismatch')
        lines += [f'        EXTRA    {n}' for n in extra]
        lines += [f'        MISSING  {n}' for n in missing]
        lines += [f'        SIZE     {n}  (expected {expected[n]["size"]}, found {got[n]})' for n in wrong]
        if sub == '.':
            lines += [f'        allowed  {n}  (not ours, kept on purpose)' for n in sorted(set(got) & allow)]
    for sub, ds in dirs.items():
        for x in ds:
            if x not in man['folders']:
                lines.append(f'FAIL  {sub}/: unexpected folder {x}/')
                ok = False
    return ok, lines


def cmd_check(a):
    man = json.load(open(a.manifest))
    if a.dir:
        files, dirs = scan_local(a.dir)
        where = a.dir
    elif a.listing:
        files, dirs = scan_listing(a.listing)
        where = 'remote listing(s): ' + ', '.join(a.listing)
    else:
        raise SystemExit('give --dir or --listing')
    ok, lines = compare(man, files, dirs)
    print(f'verify_delivery {VERSION} - {where}')
    print('\n'.join(lines))
    print('approved files:')
    for sub, names in man['folders'].items():
        ids = sorted({stem_id(n) for n in names})
        print(f'  {sub}/ ({len(names)}): ' + ' '.join(ids))
    print('RESULT: ' + ('PASS - folder holds exactly the approved files' if ok
                        else 'FAIL - do NOT report this delivery as done'))
    sys.exit(0 if ok else 3)


def main():
    ap = argparse.ArgumentParser(description=f'verify_delivery {VERSION}')
    sp = ap.add_subparsers(dest='cmd', required=True)
    m = sp.add_parser('manifest')
    m.add_argument('delivery_dir')
    m.add_argument('--approved', help='comma list of approved stems / 4-digit numbers')
    m.add_argument('--allow-extra', nargs='*', help='file names allowed in the root that are not ours')
    m.set_defaults(fn=cmd_manifest)
    c = sp.add_parser('check')
    c.add_argument('--manifest', required=True)
    c.add_argument('--dir')
    c.add_argument('--listing', action='append', help='SUB=listing.json (SUB is . for the root)')
    c.set_defaults(fn=cmd_check)
    a = ap.parse_args()
    a.fn(a)


if __name__ == '__main__':
    main()
