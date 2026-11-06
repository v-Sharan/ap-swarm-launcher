"""PyInstaller entry point for the swarm launcher GUI.

When frozen by ``ap-sitl-swarm-gui.spec``, the GUI ships in one folder
together with the console launcher and the SITL simulators::

    AP-SITL-Swarm-Launcher/
        AP SITL Swarm Launcher.exe   <- this entry point (windowed)
        ap-sitl-swarm.exe            <- launcher CLI (console, run hidden)
        bin/windows/...              <- ArduCopter.exe, ArduPlane.exe + DLLs
        scripts/get_windows_sitl.ps1 <- updates bin/windows
        _internal/                   <- Python runtime

`ap_swarm_launcher.gui` itself assumes a source checkout (it runs
``python -m ap_swarm_launcher.cli`` and finds ``bin/windows`` in the repo), so
this file points it at the files next to the executable instead, without
modifying the GUI module.
"""

import os
import sys
from pathlib import Path

import ap_swarm_launcher.gui as gui

LAUNCHER_EXE_NAME = "ap-sitl-swarm.exe"


def configure_for_frozen_app() -> None:
    app_dir = Path(sys.executable).resolve().parent

    gui.REPO_ROOT = app_dir
    gui.SITL_DIR = app_dir / "bin" / "windows"

    # Keep the drones' working files out of the application folder, which
    # may not be writable (e.g. when placed under Program Files)
    local_appdata = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    gui.DATA_DIR = local_appdata / "ap-swarm-launcher" / "swarm-data"

    launcher = app_dir / LAUNCHER_EXE_NAME
    module_prefix = ["-u", "-m", "ap_swarm_launcher.cli"]
    build_command = gui.SwarmLauncherApp._build_command

    def _build_command(self):
        # "<python> -u -m ap_swarm_launcher.cli ARGS" -> "ap-sitl-swarm.exe ARGS"
        cmd = build_command(self)
        if cmd[1:4] != module_prefix:
            raise RuntimeError(f"unexpected launcher command: {cmd!r}")
        if not launcher.is_file():
            raise ValueError(f"Launcher not found next to the GUI:\n{launcher}")
        return [str(launcher), *cmd[4:]]

    gui.SwarmLauncherApp._build_command = _build_command


if __name__ == "__main__":
    if getattr(sys, "frozen", False):
        configure_for_frozen_app()
    gui.main()
