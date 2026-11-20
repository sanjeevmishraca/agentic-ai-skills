# PyInstaller spec — run from the vanyajeev/ folder:  pyinstaller packaging/vanyajeev.spec
import glob, os
from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
TOOLS = os.path.join(ROOT, '..', 'tools')
pipeline = [(f, 'vanyajeev/pipeline') for f in
            [os.path.join(TOOLS, n) for n in ('photo_develop.py', 'expert_finish.py', 'upscale_print.py', 'calib.json')]]
assets = [(f, 'vanyajeev/assets') for f in glob.glob(os.path.join(ROOT, 'vanyajeev', 'assets', '*'))]

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],                     # pipeline is loaded from vanyajeev/pipeline as plain files (keeps calib.json beside it)
    binaries=collect_dynamic_libs('rawpy'),
    datas=pipeline + assets + [(os.path.join(TOOLS, 'calib.json'), '.')],
    hiddenimports=collect_submodules('rawpy') + ['argparse', 'json', 'math', 'tempfile', 'zipfile', 'cv2', 'PIL.ImageCms', 'PIL.ImageOps'],
    excludes=['tkinter', 'matplotlib', 'pkg_resources', 'setuptools', 'IPython', 'scipy', 'pandas', 'imageio', 'imageio_ffmpeg',
              'skimage', 'sklearn', 'lxml', 'numba', 'llvmlite'] + [
        'PySide6.' + m for m in ('QtWebEngineCore', 'QtWebEngineWidgets', 'QtWebEngineQuick', 'QtWebChannel', 'QtWebSockets',
                                 'QtQuick', 'QtQuickWidgets', 'QtQuick3D', 'QtQml', 'Qt3DCore', 'Qt3DRender', 'Qt3DExtras',
                                 'QtCharts', 'QtDataVisualization', 'QtGraphs', 'QtMultimedia', 'QtMultimediaWidgets',
                                 'QtBluetooth', 'QtNfc', 'QtSensors', 'QtSerialPort', 'QtPositioning', 'QtLocation', 'QtSql',
                                 'QtTest', 'QtDesigner', 'QtHelp', 'QtPdf', 'QtPdfWidgets', 'QtRemoteObjects', 'QtScxml',
                                 'QtSpatialAudio', 'QtTextToSpeech', 'QtHttpServer', 'QtOpenGL', 'QtOpenGLWidgets', 'QtSvg',
                                 'QtSvgWidgets', 'QtUiTools', 'QtXml', 'QtConcurrent', 'QtDBus', 'QtNetworkAuth')],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Vanyajeev', console=False,
          icon=os.path.join(ROOT, 'vanyajeev', 'assets', 'icon.ico'),
          version=os.path.join(ROOT, 'packaging', 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='Vanyajeev')
