"""Assemble an MSIX layout from dist/Vanyajeev and pack it with makeappx (Windows SDK).

Identity values must match the app reserved in Partner Center. Set them as environment variables
(GitHub repo variables): MSIX_IDENTITY_NAME, MSIX_PUBLISHER (e.g. CN=XXXXXXXX-...), MSIX_PUBLISHER_DISPLAY.
The Store re-signs the package, so it is uploaded unsigned.
"""
import glob, os, shutil, subprocess, sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / 'dist'
version = os.environ.get('VANYAJEEV_VERSION', '1.0.0')
v4 = '.'.join((version.split('.') + ['0', '0', '0'])[:3]) + '.0'      # Store requires the 4th part = 0
ident = os.environ.get('MSIX_IDENTITY_NAME') or 'Vanyajeev.Preview'
pub = os.environ.get('MSIX_PUBLISHER') or 'CN=VanyajeevPreview'
pubd = os.environ.get('MSIX_PUBLISHER_DISPLAY') or 'Sanjeev Mishra'

layout = DIST / 'msix_layout'
shutil.rmtree(layout, ignore_errors=True)
shutil.copytree(DIST / 'Vanyajeev', layout / 'Vanyajeev')
(layout / 'Assets').mkdir()
icon = Image.open(ROOT / 'vanyajeev' / 'assets' / 'icon.png').convert('RGBA')
for name, (w, h) in {'StoreLogo': (50, 50), 'Square44x44Logo': (44, 44), 'Square150x150Logo': (150, 150),
                     'Wide310x150Logo': (310, 150)}.items():
    canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    s = min(w, h)
    canvas.paste(icon.resize((s, s), Image.LANCZOS), ((w - s) // 2, (h - s) // 2))
    canvas.save(layout / 'Assets' / f'{name}.png')
m = (ROOT / 'packaging' / 'msix' / 'AppxManifest.template.xml').read_text(encoding='utf-8')
m = m.replace('__IDENTITY_NAME__', ident).replace('__PUBLISHER__', pub).replace('__PUBLISHER_DISPLAY__', pubd).replace('__VERSION__', v4)
(layout / 'AppxManifest.xml').write_text(m, encoding='utf-8')

tools = sorted(glob.glob(r'C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\makeappx.exe'))
if not tools:
    sys.exit('makeappx.exe not found (install the Windows 10/11 SDK)')
out = DIST / f'Vanyajeev-{version}.msix'
subprocess.check_call([tools[-1], 'pack', '/o', '/d', str(layout), '/p', str(out)])
print('MSIX:', out, '| identity', ident, '| publisher', pub)
