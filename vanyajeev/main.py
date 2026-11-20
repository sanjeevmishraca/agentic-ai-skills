"""Vanyajeev entry point.  `Vanyajeev.exe --selftest` runs a headless end-to-end check (used by CI)."""
import sys


def selftest():
    import tempfile, os
    from pathlib import Path
    import numpy as np
    from PIL import Image
    from vanyajeev import engine as E
    import rawpy  # noqa: F401  (RAW decoder must be bundled)
    assert E._CAL.get('lut') is not None and E.GAINS.get('exp', 1) != 1, 'calibration (calib.json) not loaded'
    print('calibration loaded from', E.pdv.HERE)
    d = Path(tempfile.mkdtemp())
    yy, xx = np.mgrid[0:800, 0:1200]
    img = np.stack([(xx / 1200 * 200 + 30), (yy / 800 * 150 + 50), np.full_like(xx, 90.0)], -1)
    img[300:600, 450:750] = (210, 160, 60)          # a "subject"
    Image.fromarray(img.astype(np.uint8)).save(d / 'test.jpg', quality=95)
    sig = Image.new('RGBA', (300, 120), (0, 0, 0, 0)); sig.paste((0, 0, 0, 255), (20, 50, 280, 70)); sig.save(d / 'sig.png')
    ph = E.new_photo(d / 'test.jpg'); ph.settings.look = True; ph.settings.crop = (0.1, 0.1, 0.8, 0.8)
    E.render_preview(ph)
    out = E.export(ph, E.ExportOptions(out_dir=d / 'out', print_factor=2, signature=str(d / 'sig.png'), artist='Selftest'))
    assert len(out) == 4 and all(Path(p).exists() for p in out), out
    w, h = Image.open(out[2]).size
    assert (w, h) == (1920, 1280), (w, h)
    print('SELFTEST OK', [Path(p).name for p in out])
    return 0


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        sys.exit(selftest())
    from vanyajeev.app import main
    main()
