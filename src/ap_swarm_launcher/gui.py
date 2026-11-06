"""Graphical front-end for the ArduPilot SITL swarm launcher.

Lets the user pick how many vehicles of each type to simulate, the home
location and heading of the formation and the IP address where the drones
send their UDP telemetry, then runs ``ap-sitl-swarm`` in the background and
shows its output.

Start it with ``uv run ap-sitl-swarm-gui`` or via the desktop shortcut created
by ``scripts\\create_gui_shortcut.ps1``.
"""

from __future__ import annotations

import ipaddress
import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Dict, List, Optional

from ap_swarm_launcher.constants import DEFAULT_GCS_PORT

IS_WINDOWS = sys.platform == "win32"

REPO_ROOT = Path(__file__).resolve().parents[2]
"""Root of the source checkout (the package is installed in editable mode)."""

SITL_DIR = REPO_ROOT / "bin" / "windows" if IS_WINDOWS else REPO_ROOT / "bin"
"""Folder holding the SITL executables (see scripts/get_windows_sitl.ps1)."""

_APPDATA = Path(os.environ.get("APPDATA") or Path.home() / ".config")

SETTINGS_FILE = _APPDATA / "ap-swarm-launcher" / "gui.json"
DATA_DIR = REPO_ROOT / "swarm-data"
"""Working folder of the simulated drones (EEPROM, logs, generated
default.param per drone); wiped before every launch so each run starts from
the embedded default parameters, like the CLI does with its temporary folder.
Kept inside the repository rather than under %LOCALAPPDATA%, which the
Microsoft Store Python silently redirects into its package folder."""

CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

MAX_LOG_LINES = 5000


@dataclass(frozen=True)
class VehicleType:
    key: str
    label: str
    executable: str
    """Path of the SITL executable, relative to `SITL_DIR`."""
    model: str
    param_file: str
    """Embedded default parameter file that sitl.py picks for this executable
    (shown for information only)."""
    default_count: int


VEHICLE_TYPES = (
    VehicleType(
        "quadplane",
        "QuadPlane",
        "ArduPlane/ArduPlane.exe" if IS_WINDOWS else "arduplane",
        "quadplane",
        "quadplane.parm",
        5,
    ),
    VehicleType(
        "copter",
        "Copter (quad)",
        "ArduCopter/ArduCopter.exe" if IS_WINDOWS else "arducopter",
        "quad",
        "copter.parm",
        5,
    ),
)

DEFAULT_SETTINGS = {
    "counts": {vt.key: vt.default_count for vt in VEHICLE_TYPES},
    "lat": "12.928852",
    "lon": "80.046431",
    "alt": "0",
    "heading": "0",
    "ip": "127.0.0.1",
    "per_row": "5",
}


def local_ipv4_addresses() -> List[str]:
    """Returns 127.0.0.1 followed by the IPv4 addresses of this machine."""
    result = ["127.0.0.1"]
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0])
            if ip not in result:
                result.append(ip)
    except OSError:
        pass
    return result


def load_settings() -> dict:
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return settings
    if isinstance(stored, dict):
        for key in ("lat", "lon", "alt", "heading", "ip", "per_row"):
            if isinstance(stored.get(key), str):
                settings[key] = stored[key]
        if isinstance(stored.get("counts"), dict):
            for key, value in stored["counts"].items():
                if key in settings["counts"] and isinstance(value, int):
                    settings["counts"][key] = value
    return settings


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def _parse_float(text: str, name: str, low: float, high: float) -> float:
    try:
        value = float(text.strip())
    except ValueError:
        raise ValueError(f"{name} must be a number") from None
    if not low <= value <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}")
    return value


class SwarmLauncherApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ArduPilot SITL Swarm Launcher")
        self.minsize(640, 560)

        self._process: Optional[subprocess.Popen] = None
        self._output: "queue.Queue[tuple[str, object]]" = queue.Queue()
        self._stopping = False

        settings = load_settings()

        self._count_vars: Dict[str, tk.StringVar] = {}
        self._sysid_labels: Dict[str, ttk.Label] = {}
        self._lat = tk.StringVar(value=settings["lat"])
        self._lon = tk.StringVar(value=settings["lon"])
        self._alt = tk.StringVar(value=settings["alt"])
        self._heading = tk.StringVar(value=settings["heading"])
        self._per_row = tk.StringVar(value=settings["per_row"])
        self._grid_hint = tk.StringVar()
        self._ip = tk.StringVar(value=settings["ip"])
        self._status = tk.StringVar(value="Stopped")
        self._ports_hint = tk.StringVar()

        self._build_ui(settings)
        self._update_sysids()
        self._update_ports_hint()

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._drain_output)

    # ------------------------------------------------------------------ UI

    def _build_ui(self, settings: dict) -> None:
        pad = {"padx": 6, "pady": 3}
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(4, weight=1)

        # Vehicles
        vehicles = ttk.LabelFrame(root, text="Vehicles", padding=6)
        vehicles.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for col, heading in enumerate(("Type", "Count", "Param file", "System IDs", "Simulator")):
            ttk.Label(vehicles, text=heading, font=("Segoe UI", 9, "bold")).grid(
                row=0, column=col, sticky="w", **pad
            )
        for row, vt in enumerate(VEHICLE_TYPES, start=1):
            var = tk.StringVar(value=str(settings["counts"].get(vt.key, 0)))
            var.trace_add("write", lambda *_: self._update_sysids())
            self._count_vars[vt.key] = var

            ttk.Label(vehicles, text=vt.label).grid(row=row, column=0, sticky="w", **pad)
            ttk.Spinbox(vehicles, from_=0, to=50, width=6, textvariable=var).grid(
                row=row, column=1, sticky="w", **pad
            )
            ttk.Label(vehicles, text=vt.param_file).grid(row=row, column=2, sticky="w", **pad)
            sysid = ttk.Label(vehicles, text="")
            sysid.grid(row=row, column=3, sticky="w", **pad)
            self._sysid_labels[vt.key] = sysid

            exe = SITL_DIR / vt.executable
            found = exe.is_file()
            ttk.Label(
                vehicles,
                text="found" if found else "MISSING",
                foreground="green" if found else "red",
            ).grid(row=row, column=4, sticky="w", **pad)

        row = len(VEHICLE_TYPES) + 1
        ttk.Separator(vehicles).grid(row=row, column=0, columnspan=5, sticky="ew", pady=4)
        ttk.Label(vehicles, text="Drones per row").grid(row=row + 1, column=0, sticky="w", **pad)
        ttk.Spinbox(vehicles, from_=1, to=100, width=6, textvariable=self._per_row).grid(
            row=row + 1, column=1, sticky="w", **pad
        )
        ttk.Label(vehicles, textvariable=self._grid_hint, foreground="gray25").grid(
            row=row + 1, column=2, columnspan=3, sticky="w", **pad
        )
        self._per_row.trace_add("write", lambda *_: self._update_sysids())

        # Home location
        home = ttk.LabelFrame(root, text="Home location", padding=6)
        home.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        fields = (
            ("Latitude (deg)", self._lat),
            ("Longitude (deg)", self._lon),
            ("Altitude AMSL (m)", self._alt),
            ("Heading (deg)", self._heading),
        )
        for i, (label, var) in enumerate(fields):
            r, c = divmod(i, 2)
            ttk.Label(home, text=label).grid(row=r, column=c * 2, sticky="w", **pad)
            ttk.Entry(home, textvariable=var, width=16).grid(
                row=r, column=c * 2 + 1, sticky="w", **pad
            )

        # Telemetry
        telem = ttk.LabelFrame(root, text="Telemetry (UDP out)", padding=6)
        telem.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(telem, text="Ground station IP").grid(row=0, column=0, sticky="w", **pad)
        ip_box = ttk.Combobox(
            telem, textvariable=self._ip, values=local_ipv4_addresses(), width=18
        )
        ip_box.grid(row=0, column=1, sticky="w", **pad)
        self._ip.trace_add("write", lambda *_: self._update_ports_hint())
        ttk.Label(telem, textvariable=self._ports_hint, foreground="gray25").grid(
            row=1, column=0, columnspan=3, sticky="w", **pad
        )

        # Controls
        controls = ttk.Frame(root)
        controls.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        self._start_btn = ttk.Button(controls, text="Start simulation", command=self._start)
        self._start_btn.pack(side="left")
        self._stop_btn = ttk.Button(
            controls, text="Stop", command=self._stop, state="disabled"
        )
        self._stop_btn.pack(side="left", padx=6)
        ttk.Button(controls, text="Clear log", command=self._clear_log).pack(side="left")
        ttk.Label(controls, textvariable=self._status).pack(side="right")

        # Log
        self._log = ScrolledText(root, height=14, state="disabled", font=("Consolas", 9))
        self._log.grid(row=4, column=0, sticky="nsew")

    def _counts(self) -> Dict[str, int]:
        result = {}
        for key, var in self._count_vars.items():
            try:
                result[key] = max(0, int(var.get().strip() or 0))
            except ValueError:
                result[key] = 0
        return result

    def _update_sysids(self) -> None:
        next_id = 1
        counts = self._counts()
        for vt in VEHICLE_TYPES:
            n = counts[vt.key]
            label = self._sysid_labels[vt.key]
            if n <= 0:
                label.configure(text="-")
            elif n == 1:
                label.configure(text=f"{next_id}")
            else:
                label.configure(text=f"{next_id} - {next_id + n - 1}")
            next_id += max(n, 0)

        total = next_id - 1
        per_row = self._per_row_value()
        if total <= 0:
            self._grid_hint.set("")
        elif per_row is None:
            self._grid_hint.set("enter a whole number of 1 or more")
        else:
            rows = -(-total // per_row)
            self._grid_hint.set(
                f"{total} drone(s) -> {rows} row(s) of up to {min(per_row, total)}"
            )

    def _per_row_value(self) -> Optional[int]:
        """Returns the number of drones per row, or ``None`` if invalid."""
        try:
            value = int(self._per_row.get().strip())
        except ValueError:
            return None
        return value if value >= 1 else None

    def _update_ports_hint(self) -> None:
        ip = self._ip.get().strip() or "?"
        self._ports_hint.set(
            f"All drones -> {ip}:{DEFAULT_GCS_PORT}    "
            f"Drone N only -> {ip}:{DEFAULT_GCS_PORT}+N"
        )

    def _append_log(self, text: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", text.rstrip("\r\n") + "\n")
        lines = int(self._log.index("end-1c").split(".")[0])
        if lines > MAX_LOG_LINES:
            self._log.delete("1.0", f"{lines - MAX_LOG_LINES}.0")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _current_settings(self) -> dict:
        return {
            "counts": self._counts(),
            "lat": self._lat.get().strip(),
            "lon": self._lon.get().strip(),
            "alt": self._alt.get().strip(),
            "heading": self._heading.get().strip(),
            "ip": self._ip.get().strip(),
            "per_row": self._per_row.get().strip(),
        }

    # ------------------------------------------------------------- Launching

    def _build_command(self) -> List[str]:
        """Validates the inputs and returns the launcher command line.

        Raises:
            ValueError: if any input is invalid
        """
        counts = self._counts()
        total = sum(counts.values())
        if total <= 0:
            raise ValueError("Set the count of at least one vehicle type above 0.")
        if total > 100:
            raise ValueError("At most 100 vehicles can be simulated at once.")

        per_row = self._per_row_value()
        if per_row is None:
            raise ValueError("Drones per row must be a whole number of 1 or more.")

        lat = _parse_float(self._lat.get(), "Latitude", -90, 90)
        lon = _parse_float(self._lon.get(), "Longitude", -180, 180)
        alt = _parse_float(self._alt.get(), "Altitude", -500, 9000)
        heading = _parse_float(self._heading.get(), "Heading", 0, 360) % 360

        ip_text = self._ip.get().strip()
        try:
            ip = ipaddress.IPv4Address(ip_text)
        except ValueError:
            raise ValueError(f"Ground station IP is not a valid IPv4 address: {ip_text!r}") from None
        if IS_WINDOWS and ip.is_unspecified:
            raise ValueError(
                "0.0.0.0 does not work as a UDP destination on Windows. "
                "Use 127.0.0.1 or the IP of the ground station computer."
            )

        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")

        cmd = [
            str(python),
            "-u",
            "-m",
            "ap_swarm_launcher.cli",
            "--home",
            f"{lat:.7f},{lon:.7f},{alt:g},{heading:g}",
            "--ip",
            str(ip),
            "--num-drones-per-row",
            str(per_row),
            "-d",
            str(DATA_DIR),
        ]

        missing = []
        for vt in VEHICLE_TYPES:
            n = counts[vt.key]
            if n <= 0:
                continue
            exe = SITL_DIR / vt.executable
            if not exe.is_file():
                missing.append(str(exe))
            cmd.extend(["--vehicle", f"{exe}:{vt.model}:{n}"])

        if missing:
            hint = (
                "Run scripts\\get_windows_sitl.ps1 in the repository first."
                if IS_WINDOWS
                else "Put the SITL binaries into the bin folder first."
            )
            raise ValueError("SITL executable not found:\n" + "\n".join(missing) + "\n\n" + hint)

        return cmd

    def _start(self) -> None:
        if self._process is not None:
            return

        try:
            cmd = self._build_command()
        except ValueError as ex:
            messagebox.showerror("Invalid settings", str(ex), parent=self)
            return

        save_settings(self._current_settings())

        try:
            if DATA_DIR.exists():
                shutil.rmtree(DATA_DIR)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            messagebox.showerror(
                "Cannot prepare data folder",
                f"{DATA_DIR}\n\n{ex}\n\nAre simulators from a previous run still running?",
                parent=self,
            )
            return

        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
        kwds: dict = {}
        if IS_WINDOWS:
            # Hidden console shared by the launcher and all SITL processes
            kwds["creationflags"] = CREATE_NO_WINDOW
        else:
            kwds["start_new_session"] = True

        self._append_log("$ " + subprocess.list2cmdline(cmd))
        try:
            self._process = subprocess.Popen(
                cmd,
                cwd=str(REPO_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                **kwds,
            )
        except OSError as ex:
            self._process = None
            messagebox.showerror("Failed to start", str(ex), parent=self)
            return

        self._stopping = False
        threading.Thread(
            target=self._pump_output, args=(self._process,), daemon=True
        ).start()

        total = sum(self._counts().values())
        self._status.set(f"Running {total} vehicle(s)")
        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")

    def _pump_output(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for raw in iter(process.stdout.readline, b""):
            self._output.put(("line", raw.decode("utf-8", "replace")))
        code = process.wait()
        self._output.put(("exit", code))

    def _drain_output(self) -> None:
        try:
            while True:
                kind, payload = self._output.get_nowait()
                if kind == "line":
                    self._append_log(str(payload))
                elif kind == "exit":
                    self._on_process_exit(int(payload))  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self.after(100, self._drain_output)

    def _on_process_exit(self, code: int) -> None:
        if self._stopping:
            self._append_log("--- simulation stopped ---")
        else:
            self._append_log(f"--- launcher exited with code {code} ---")
        self._process = None
        self._stopping = False
        self._status.set("Stopped")
        self._start_btn.configure(state="normal")
        self._stop_btn.configure(state="disabled")

    def _stop(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._stopping = True
        self._status.set("Stopping...")
        self._stop_btn.configure(state="disabled")
        if IS_WINDOWS:
            # Kill the launcher together with every SITL process it started
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGINT)
            except OSError:
                process.terminate()

    def _on_close(self) -> None:
        if self._process is not None and self._process.poll() is None:
            if not messagebox.askyesno(
                "Quit", "The simulation is running. Stop it and quit?", parent=self
            ):
                return
            self._stop()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        save_settings(self._current_settings())
        self.destroy()


def main() -> None:
    if IS_WINDOWS:
        try:
            # Crisp text on high-DPI laptop screens
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    app = SwarmLauncherApp()
    app.mainloop()


if __name__ == "__main__":
    main()
