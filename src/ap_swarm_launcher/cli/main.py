"""Command-line interface entrypoint for the ArduPilot SITL swarm launcher tool."""

import sys
from argparse import ArgumentParser
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from random import normalvariate
from typing import List, Optional, Sequence, Tuple, Union

from ap_swarm_launcher.constants import DEFAULT_GCS_PORT, DEFAULT_LISTENER_PORT
from ap_swarm_launcher.formations import create_grid_formation
from ap_swarm_launcher.locations import (
    DEFAULT_LOCATION,
    LocationDefinition,
    parse_location,
)
from ap_swarm_launcher.sitl import SimulatedDroneSwarm
from ap_swarm_launcher.utils import route_local_broadcast_traffic_to_multicast
from ap_swarm_launcher.network import NetworkIP


def parse_parameter(value: str) -> Union[Path, Tuple[str, float]]:
    name, sep, value = value.partition("=")
    if sep:
        return name.strip(), float(value)
    else:
        path = Path(name.strip())
        if not path.is_file():
            raise RuntimeError(f"Param file does not exist: {name!r}")
        return path


@dataclass
class VehicleGroup:
    """A group of identical simulated drones that share the same SITL
    executable and vehicle model within a (possibly mixed) swarm.
    """

    executable: Path
    model: Optional[str] = None
    count: int = 1


def parse_vehicle_spec(value: str) -> VehicleGroup:
    """Parses a ``--vehicle`` command-line argument of the form
    ``EXECUTABLE[:MODEL[:COUNT]]`` into a `VehicleGroup`.

    MODEL defaults to the SITL executable's own default model (e.g. 'quad'
    for ArduCopter) when omitted, and COUNT defaults to 1 when omitted. This
    allows mixing different vehicle types (e.g. ArduCopter and ArduPlane /
    QuadPlane) in the same swarm by supplying `--vehicle` multiple times.
    """
    parts = value.split(":")
    if len(parts) == 1:
        executable_str, model_str, count_str = parts[0], "", "1"
    elif len(parts) == 2:
        executable_str, model_str = parts
        count_str = "1"
    elif len(parts) == 3:
        executable_str, model_str, count_str = parts
    else:
        raise RuntimeError(
            f"invalid --vehicle spec: {value!r}; expected "
            "EXECUTABLE[:MODEL[:COUNT]]"
        )

    executable_str = executable_str.strip()
    path = Path(executable_str)
    if not path.is_file():
        raise RuntimeError(f"SITL executable does not exist: {executable_str!r}")

    model = model_str.strip() or None

    count_str = count_str.strip() or "1"
    try:
        count = int(count_str)
    except ValueError:
        raise RuntimeError(
            f"invalid drone count in --vehicle spec: {count_str!r}"
        ) from None
    if count <= 0:
        raise RuntimeError(f"drone count in --vehicle spec must be positive: {count}")

    return VehicleGroup(executable=path, model=model, count=count)


def create_parser() -> ArgumentParser:
    parser = ArgumentParser(prog="ap-sitl-swarm")

    parser.add_argument(
        "--tcp-base-port",
        default=None,
        type=int,
        metavar="PORT",
        help="open TCP connections for each drone, starting from PORT",
    )
    parser.add_argument(
        "--serial-port",
        default=None,
        type=str,
        metavar="PORT",
        help="aggregate all packets from the drones to the given serial PORT",
    )
    parser.add_argument(
        "--no-udp",
        dest="use_udp",
        default=True,
        action="store_false",
        help=f"do not send status packets to UDP port {DEFAULT_GCS_PORT} on localhost",
    )
    parser.add_argument(
        "--no-multicast",
        dest="use_multicast",
        default=True,
        action="store_false",
        help="do not join multicast group to simulate broadcasting on localhost",
    )
    parser.add_argument(
        "-d",
        "--data-dir",
        default=None,
        type=Path,
        metavar="DIR",
        help="store the filesystem and parameters of the simulated drones in "
        "the given DIR. Creates a temporary directory when omitted.",
    )
    parser.add_argument(
        "--home",
        default=DEFAULT_LOCATION,
        type=parse_location,
        help=(
            "the origin and orientation of the initial formation of the swarm "
            "(latitude,longitude,amsl,orientation) or the name of a well-known "
            "location)"
        ),
    )
    parser.add_argument(
        "-m",
        "--model",
        default=None,
        type=str,
        help="The name of the vehicle model to use in the simulator (e.g., 'quad', 'JSON', 'airsim' etc.)",
        metavar="MODEL",
    )
    parser.add_argument(
        "-n",
        "--num-drones",
        default=1,
        type=int,
        help="use COUNT drones in the swarm",
        metavar="COUNT",
    )
    parser.add_argument(
        "--vehicle",
        dest="vehicles",
        action="append",
        default=[],
        type=parse_vehicle_spec,
        metavar="EXECUTABLE[:MODEL[:COUNT]]",
        help=(
            "add a group of COUNT drones running the given SITL EXECUTABLE "
            "with the given vehicle MODEL to the swarm. May be given "
            "multiple times to mix vehicle types (e.g. ArduCopter and "
            "ArduPlane/QuadPlane) in the same simulation. Combines with the "
            "positional SITL_EXECUTABLE argument (if given), which is then "
            "treated as an additional group."
        ),
    )
    parser.add_argument(
        "--num-drones-per-row",
        default=None,
        type=int,
        help="use COUNT drones per row in the takeoff grid",
        metavar="COUNT",
    )
    parser.add_argument(
        "--param",
        default=[],
        type=parse_parameter,
        action="append",
        metavar="PARAM",
        help="names of parameter files or parameters in the format NAME=VALUE that "
        "should be passed to the simulated drones, on top of the default parameter "
        "settings",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=3.0,
        metavar="DIST",
        help="use DIST meters of spacing between drones in the initial grid formation",
    )
    parser.add_argument(
        "--pos-noise",
        type=float,
        default=0.0,
        metavar="DIST",
        help=(
            "perturb the initial drone positions with Gaussian noise with a "
            "standard deviation of DIST"
        ),
    )
    parser.add_argument(
        "--yaw-noise",
        type=float,
        default=0.0,
        metavar="ANGLE",
        help=(
            "perturb the yaw angles with Gaussian noise with a standard "
            "deviation of ANGLE"
        ),
    )
    parser.add_argument(
        "--system-id-offset",
        type=int,
        default=0,
        metavar="OFFSET",
        help="offset to add to the system IDs of the simulated drones",
    )

    parser.add_argument(
        "sitl_executable",
        nargs="?",
        default=None,
        metavar="SITL_EXECUTABLE",
        help=(
            "path to the ArduPilot SITL executable to use for the whole "
            "swarm (or for one group of drones, if --vehicle is also "
            "given). May be omitted in favor of one or more --vehicle "
            "options to mix vehicle types."
        ),
    )
    return parser


async def run(
    sitl_executable: Optional[Path] = None,
    vehicles: Sequence[VehicleGroup] = (),
    data_dir: Optional[Path] = None,
    home: LocationDefinition = DEFAULT_LOCATION,
    num_drones: int = 1,
    param: Sequence[Union[Path, Tuple[str, float]]] = (),
    spacing: float = 3,
    num_drones_per_row: Optional[int] = None,
    pos_noise: float = 0.0,
    yaw_noise: float = 0.0,
    tcp_base_port: Optional[int] = None,
    serial_port: Optional[str] = None,
    use_udp: bool = True,
    use_multicast: bool = True,
    model: Optional[str] = None,
    system_id_offset: int = 0,
) -> None:
    gcs_port = DEFAULT_GCS_PORT
    listener_port = DEFAULT_LISTENER_PORT

    gcs_address = f"192.168.31.15:{gcs_port}" if use_udp else None
    multicast_address = f"239.255.67.77:{listener_port}" if use_multicast else None

    # Build the list of vehicle groups: the positional SITL_EXECUTABLE (if
    # given) forms one group using -m/--model and -n/--num-drones, and each
    # --vehicle option adds another. This is what allows mixing vehicle
    # types (e.g. ArduCopter + ArduPlane/QuadPlane) in a single swarm.
    groups: List[VehicleGroup] = []
    if sitl_executable is not None:
        groups.append(
            VehicleGroup(
                executable=Path.cwd() / sitl_executable,
                model=model,
                count=num_drones,
            )
        )
    for group in vehicles:
        groups.append(
            VehicleGroup(
                executable=Path.cwd() / group.executable,
                model=group.model,
                count=group.count,
            )
        )

    if not groups:
        raise RuntimeError(
            "no SITL executable specified; provide SITL_EXECUTABLE or at "
            "least one --vehicle option"
        )

    total_drones = sum(group.count for group in groups)

    if num_drones_per_row is None:
        num_drones_per_row = max(1, int(round(total_drones**0.5)))

    grid = create_grid_formation(num_drones_per_row, spacing, pos_noise)

    # Per-drone embedded default parameter files (e.g. quadplane.parm) are
    # now selected in sitl.py based on each drone's own executable, so only
    # the user-supplied --param overrides are passed through here.
    param_sources: List[Union[Path, str, Tuple[str, float]]] = list(param)

    port = {i: DEFAULT_GCS_PORT + i for i in range(1, total_drones + 1)}
    ip = NetworkIP.get_ip()

    async with SimulatedDroneSwarm(
        groups[0].executable,
        dir=data_dir,
        params=param_sources,
        coordinate_system=home.coordinate_system,
        amsl=home.origin.amsl,
        gcs_address=gcs_address,
        multicast_address=multicast_address,
        tcp_base_port=tcp_base_port,
        serial_port=serial_port,
        model=groups[0].model,
        start_system_id=1 + system_id_offset,
    ).use() as swarm:
        i = 0
        for group in groups:
            for _ in range(group.count):
                await swarm.add_drone(
                    swarm_output="192.168.31.15:{}".format(port[i + 1]),
                    gcs_out="{}:{}".format(ip, port[i + 1]),
                    home=grid(i),
                    heading=(home.orientation + normalvariate(0, yaw_noise)) % 360,
                    executable=group.executable,
                    model=group.model,
                )
                i += 1

        # We need to re-route broadcast traffic sent to the port of the
        # multicast address because Skybrush will send broadcast traffic
        # to 127.0.0.1
        await route_local_broadcast_traffic_to_multicast(multicast_address)


def start():
    from exceptiongroup import suppress
    from trio import run as run_async

    parser = create_parser()
    options = parser.parse_args()

    exit_code = 0
    with suppress(KeyboardInterrupt):
        exit_code = run_async(partial(run, **vars(options)))

    sys.exit(exit_code)
