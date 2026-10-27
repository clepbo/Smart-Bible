# PyInstaller build: pyinstaller smartbible.spec  ->  dist/SmartBible/SmartBible.exe
# Run scripts/build_index.py first so the model and verse index are bundled.
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [("data/bibles", "data/bibles"), ("data/famous.json", "data")]
for optional in ("data/index", "data/models"):
    if Path(optional).exists():
        datas.append((optional, optional))
binaries = []
hiddenimports = []
for package in ("fastembed", "onnxruntime", "tokenizers"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += ["pywinauto", "comtypes", "comtypes.stream"]

a = Analysis(
    ["smartbible_app.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SmartBible",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SmartBible")
