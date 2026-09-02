# PyInstaller spec for the ap-swarm-launcher CLI.
#
# Build (run on the SAME OS you want the executable for -- PyInstaller does NOT
# cross-compile):
#
#   uv add --dev pyinstaller
#   uv run pyinstaller ap-sitl-swarm.spec
#
# Output: dist/ap-sitl-swarm  (or dist\ap-sitl-swarm.exe on Windows)
#
# This only packages the LAUNCHER. It still needs a separate ArduPilot SITL
# binary (arduplane / arduplane.exe) passed as the SITL_EXECUTABLE argument.

from pathlib import Path

# Bundle the embedded *.parm files that sitl.py loads via importlib.resources.
# Explicitly listed so the Windows "*.parm:Zone.Identifier" ADS junk is skipped.
res_dir = Path("src/ap_swarm_launcher/resources")
datas = [
    (str(p), "ap_swarm_launcher/resources")
    for p in res_dir.glob("*.parm")
]

a = Analysis(
    ["scripts/pyinstaller_entry.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "netifaces",
        "exceptiongroup",
        "serial",
        "trio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ap-sitl-swarm",
    console=True,
    disable_windowed_traceback=False,
    upx=True,
)
