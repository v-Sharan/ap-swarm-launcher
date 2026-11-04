# Running ap-swarm-launcher on Windows

On Windows the launcher drives the same prebuilt ArduPilot SITL simulators
that Mission Planner uses for its Simulation tab. These are Cygwin builds
published at <https://firmware.ardupilot.org/Tools/MissionPlanner/sitl/>.
The files there are named `ArduCopter.elf`, `ArduPlane.elf` etc., but they
are really Windows executables; they are saved as `.exe` and need a set of
Cygwin runtime DLLs (`cygwin1.dll`, `cygstdc++-6.dll`, ...) in the same
folder.

No WSL, Cygwin installation or ArduPilot build environment is needed.

## Requirements

- Windows 10 or 11, 64-bit
- [Git for Windows](https://git-scm.com/download/win)
- [uv](https://docs.astral.sh/uv/) (installs a suitable Python by itself)

Install `uv` from PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen the terminal afterwards so that `uv` is on the `PATH`.

## Setup

1. Clone the repository into a normal Windows folder. Do not reuse a
   checkout that lives inside WSL: its `.venv` is a Linux virtualenv and
   will not work from Windows.

   ```powershell
   git clone https://github.com/v-Sharan/ap-swarm-launcher.git
   cd ap-swarm-launcher
   ```

2. Install the Python dependencies:

   ```powershell
   uv sync
   ```

3. Download the SITL simulators and their DLLs:

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\get_windows_sitl.ps1
   ```

   This creates:

   ```
   bin\windows\ArduCopter\ArduCopter.exe  (+ cyg*.dll)
   bin\windows\ArduPlane\ArduPlane.exe    (+ cyg*.dll)
   ```

   Options:

   | Option | Default | Meaning |
   |---|---|---|
   | `-Channel master\|beta\|stable` | `master` | Which firmware build to download (`master` is the latest development build, as used by Mission Planner's "Latest" option) |
   | `-Vehicles ArduCopter,ArduPlane,...` | `ArduCopter,ArduPlane` | Which vehicles to download (`ArduHeli`, `ArduRover`, `ArduSub` are also available) |
   | `-OutDir PATH` | `bin\windows` | Where to put the files |

   Example: `scripts\get_windows_sitl.ps1 -Channel stable`

   Re-run the script whenever you want to update the simulators.

## Running

Mixed swarm of 5 QuadPlanes and 5 quadcopters (same as `run_mixed.sh` on
Linux):

```bat
run_mixed.bat
```

Or call the launcher directly, e.g. 3 copters only:

```powershell
uv run ap-sitl-swarm bin\windows\ArduCopter\ArduCopter.exe -n 3 --num-drones-per-row 3 --home 12.928852,80.046431 --ip 127.0.0.1
```

Mixed swarm with `--vehicle EXECUTABLE[:MODEL[:COUNT]]`; full Windows paths
with a drive letter such as `C:\...` work too:

```powershell
uv run ap-sitl-swarm `
  --vehicle bin\windows\ArduPlane\ArduPlane.exe:quadplane:3 `
  --vehicle bin\windows\ArduCopter\ArduCopter.exe:quad:3 `
  --num-drones-per-row 3 --home 12.928852,80.046431 --ip 127.0.0.1
```

Run `uv run ap-sitl-swarm -h` for all options.

Press `Ctrl+C` to stop the whole swarm.

### Always pass `--ip` on Windows

`--ip` defaults to `0.0.0.0`. Linux accepts `0.0.0.0` as a destination and
delivers the packets to localhost, but Windows does not, so telemetry would
not go anywhere. Pass `--ip 127.0.0.1` (or the address of the machine
running the ground station) on Windows.

## Connecting Mission Planner

Each drone `N` (1, 2, 3, ...) sends MAVLink telemetry over UDP to:

| Destination | Contents |
|---|---|
| `IP:14550` | All drones together (SERIAL1); system ID = drone number |
| `IP:14550+N` | Drone `N` only (SERIAL2 and SERIAL4) |

To see the whole swarm in Mission Planner, choose **UDP** in the connection
drop-down, click **Connect** and enter port `14550`. Each drone appears as a
separate vehicle (system ID 1, 2, 3, ...). With `--tcp-base-port PORT`, drone
`N` additionally listens on TCP port `PORT + N - 1`.

Do not start a simulation from Mission Planner's own Simulation tab at the
same time; it uses the same ports.

## Using Mission Planner's own copy of the simulators

If you prefer, you can point the launcher at the files Mission Planner has
already downloaded instead of running `get_windows_sitl.ps1`. Mission Planner
keeps them in:

```
%USERPROFILE%\Documents\Mission Planner\sitl\
```

Mission Planner only downloads a vehicle after you have started it once from
the Simulation tab, so start a plane and a copter once there first. Then:

```powershell
uv run ap-sitl-swarm `
  --vehicle "$env:USERPROFILE\Documents\Mission Planner\sitl\ArduPlane.exe:quadplane:5" `
  --vehicle "$env:USERPROFILE\Documents\Mission Planner\sitl\ArduCopter.exe:quad:5" `
  --num-drones-per-row 5 --home 12.928852,80.046431 --ip 127.0.0.1
```

## Troubleshooting

- **Windows Firewall prompt** for `ArduCopter.exe` / `ArduPlane.exe`: allow
  access, otherwise the ground station cannot receive telemetry.
- **"SITL executable does not exist"**: run `scripts\get_windows_sitl.ps1`
  first, and run the command from the repository root.
- **"The code execution cannot proceed because cygwin1.dll was not found"**:
  the DLLs must be in the same folder as the `.exe`. Re-run the download
  script.
- **`running scripts is disabled on this system`**: start the script with
  `powershell -ExecutionPolicy Bypass -File ...` as shown above.
- **No telemetry in Mission Planner**: check that you passed
  `--ip 127.0.0.1` and that you connected to UDP port `14550`.
- **Behaviour differs from Linux**: the `master` channel is the latest
  development build, which may be newer than your Linux binaries. Try
  `-Channel stable`.
