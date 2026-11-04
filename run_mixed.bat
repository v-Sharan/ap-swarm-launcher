@echo off
REM Windows equivalent of run_mixed.sh. Uses the Mission Planner (Cygwin)
REM SITL binaries downloaded by scripts\get_windows_sitl.ps1.
cd /d "%~dp0"
uv run ap-sitl-swarm ^
  --vehicle bin\windows\ArduPlane\ArduPlane.exe:quadplane:5 ^
  --vehicle bin\windows\ArduCopter\ArduCopter.exe:quad:5 ^
  --num-drones-per-row 5 --home 12.928852,80.046431
