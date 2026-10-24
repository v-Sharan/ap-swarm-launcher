# ap-swarm-launcher

Simplified ArduPilot SITL launcher for multi-drone simulations. Runs multiple
ArduPilot SITL instances in parallel, managed by a central process supervisor
that merges the standard output streams of individual processes and configures
the SITL instances to start the drones from a grid-like formation.

## Installation

We use `uv` to manage a Python virtual environment that will contain all
the dependencies. Install `uv` first if you don't have it yet, then follow
these steps:

1. Clone this repository.

2. Run `uv sync` to create a virtualenv and install all the dependencies
   in it.

3. Run `uv run ap-sitl-swarm SITL_PATH` to launch a single SITL instance
   with a pre-compiled SITL executable at `${SITL_PATH}`. Use the `-h` switch
   for more options.

Tested on Linux and macOS. May or may not work on Windows.

## Mixing vehicle types

By default, all drones in the swarm run the same SITL executable and vehicle
model, taken from the positional `SITL_EXECUTABLE` argument plus `-m/--model`
and `-n/--num-drones`.

To mix vehicle types (e.g. run some ArduPlane/QuadPlane drones alongside some
ArduCopter drones in the same simulation), use one or more `--vehicle`
options instead, each in the form `EXECUTABLE[:MODEL[:COUNT]]`:

```sh
uv run ap-sitl-swarm \
  --vehicle ../ardupilot/build/sitl/bin/arduplane:quadplane:3 \
  --vehicle ../ardupilot/build/sitl/bin/arducopter:quad:3 \
  --num-drones-per-row 3 --home 12.928852,80.046431
```

`MODEL` and `COUNT` are optional and default to the executable's own default
model and a count of 1, respectively. `--vehicle` can be combined with the
positional `SITL_EXECUTABLE` argument, which is then treated as one more
group. All groups share the same takeoff grid, home location, and system ID
sequence; each drone's SITL defaults (e.g. the embedded QuadPlane tuning
parameters) are chosen automatically based on its own executable.

## License

Copyright 2022-2024 CollMot Robotics Ltd.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
