# PyInstaller spec for the Windows GUI build of ap-swarm-launcher.
#
# Build on Windows, from the repository root, after
# `scripts\get_windows_sitl.ps1` has downloaded the simulators:
#
#   uv run pyinstaller --noconfirm ap-sitl-swarm-gui.spec
#
# Output: dist\AP-SITL-Swarm-Launcher\  (copy or zip the whole folder)
#
#   AP SITL Swarm Launcher.exe   GUI (scripts/pyinstaller_gui_entry.py)
#   ap-sitl-swarm.exe            launcher CLI the GUI runs in a hidden console
#                                (scripts/pyinstaller_entry.py); it needs a
#                                console so that the SITL processes it starts
#                                share it instead of each opening a window
#   bin\windows\                 SITL simulators, copied from the repository
#   scripts\get_windows_sitl.ps1 re-downloads / updates bin\windows
#
# A one-folder build is used instead of --onefile: Stop kills the launcher
# process tree, which would leave a onefile build's temporary extraction
# folder behind on every run.

import shutil
from pathlib import Path

APP_NAME = "AP-SITL-Swarm-Launcher"
ROOT = Path(SPECPATH)

# Embedded *.parm files that sitl.py loads via importlib.resources. Listed
# explicitly so that "*.parm:Zone.Identifier" alternate data streams are skipped.
datas = [
    (str(p), "ap_swarm_launcher/resources")
    for p in (ROOT / "src" / "ap_swarm_launcher" / "resources").glob("*.parm")
]

common = dict(
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=datas,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
)

gui_a = Analysis(
    [str(ROOT / "scripts" / "pyinstaller_gui_entry.py")],
    hiddenimports=["ap_swarm_launcher.gui"],
    excludes=[],
    **common,
)
cli_a = Analysis(
    [str(ROOT / "scripts" / "pyinstaller_entry.py")],
    hiddenimports=["exceptiongroup", "serial", "trio"],
    excludes=["tkinter"],
    **common,
)

gui_exe = EXE(
    PYZ(gui_a.pure),
    gui_a.scripts,
    [],
    exclude_binaries=True,
    name="AP SITL Swarm Launcher",
    console=False,
    disable_windowed_traceback=False,
    upx=False,
)
cli_exe = EXE(
    PYZ(cli_a.pure),
    cli_a.scripts,
    [("u", None, "OPTION")],  # unbuffered stdout so the GUI log is live
    exclude_binaries=True,
    name="ap-sitl-swarm",
    console=True,
    upx=False,
)

coll = COLLECT(
    gui_exe,
    gui_a.binaries,
    gui_a.datas,
    cli_exe,
    cli_a.binaries,
    cli_a.datas,
    name=APP_NAME,
    upx=False,
)

# Ship the simulators and their download script next to the executables
dist_dir = Path(DISTPATH) / APP_NAME
sitl_src = ROOT / "bin" / "windows"
if sitl_src.is_dir():
    shutil.copytree(sitl_src, dist_dir / "bin" / "windows", dirs_exist_ok=True)
else:
    print(f"WARNING: {sitl_src} not found; run scripts\\get_windows_sitl.ps1 first")
(dist_dir / "scripts").mkdir(exist_ok=True)
shutil.copy2(ROOT / "scripts" / "get_windows_sitl.ps1", dist_dir / "scripts")
