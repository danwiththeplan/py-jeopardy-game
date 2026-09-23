# PyInstaller build for the Windows executable. Run on Windows:
#
#     poetry run pip install pyinstaller
#     poetry run pyinstaller jeopardy.spec
#
# The result is dist/Jeopardy.exe, a single file that needs no Python install.

a = Analysis(
    ["src/jeopardy/gui.py"],
    pathex=["src"],
    datas=[("src/jeopardy/resources/*.wav", "jeopardy/resources")],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="Jeopardy",
    console=False,      # no black terminal window behind the game
    upx=False,
)
