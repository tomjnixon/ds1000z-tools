from .exceptions import UserError


def connect(args):
    import pyvisa

    rm = pyvisa.ResourceManager(args.visa)

    name = args.name
    if args.address is not None:
        name = f"TCPIP::{args.address}::INSTR"

    if name is None:
        from .discover import discover

        res = discover(rm, "RIGOL TECHNOLOGIES,DS1...Z")
        if res is None:
            raise UserError("could not discover a scope, and none was specified")
    else:
        res = rm.open_resource(name)

    from .scope import DS1000Z

    return rm, DS1000Z(res)


def _get_write_formats():
    import numpy as np

    return dict(
        npy=np.save,
    )


write_formats = _get_write_formats()
default_write_format = "npy"


def detect_format(fname: str) -> str:
    from pathlib import Path

    format = Path(fname).suffix.lstrip(".")
    if not format:
        raise UserError("no format specified and file name does not have an extension")
    if format not in write_formats:
        raise UserError(f"unknown format {format} (from filename)")
    return format


def auto_fname(format: str) -> str:
    import datetime
    from pathlib import Path
    import sys

    iso_date = datetime.datetime.now().replace(microsecond=0).isoformat()

    fname = f"ds1000z-{iso_date}.{format}"
    if Path(fname).exists():
        raise UserError("not overwriting existing file with auto-generated name")

    print(fname, file=sys.stderr)
    return fname


def get_fname_format(args) -> tuple[str, str]:
    fname = args.fname
    format = args.format

    # if format is not None and format not in write_formats:
    #     raise UserError("unknown format:

    # fizzbuzz scenario IRL! it's tidier to cover all cases explicitly rather
    # than try to simplify this
    if fname is not None and format is not None:
        pass
    elif fname is None and format is not None:
        fname = auto_fname(format)
    elif fname is not None and format is None:
        format = detect_format(fname)
    elif fname is None and format is None:
        format = default_write_format
        fname = auto_fname(format)

    return fname, format


def parse_channels(channels_arg):
    if channels_arg is None:
        return None

    channels = channels_arg.split(",")

    parsed = []
    for channel in channels:
        channel = channel.strip()
        if channel.isdigit():
            channel = "CHAN" + channel
        # TODO: validate?

        parsed.append(channel)

    return parsed


def save_data(args):
    rm, scope = connect(args)

    channels = parse_channels(args.channels)

    if args.screen:
        data = scope.get_data_screen(channels)
    else:
        data = scope.get_data_memory(channels)

    from .scope import process_data

    data = process_data(data, to_voltage=not args.raw, to_dict=True)

    fname, format = get_fname_format(args)
    write_formats[format](fname, data)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--visa", default="@py", help="pyvisa VISA implementation to use"
    )

    host_group = parser.add_mutually_exclusive_group()
    host_group.add_argument("--address", "-a", help="scope host name or IP")
    host_group.add_argument("--name", "-n", help="VISA resource name to connect to")

    subparsers = parser.add_subparsers(title="subcommands", required=True)

    p_save_data = subparsers.add_parser(
        "save-data", help="save data from screen or memory to a file"
    )
    p_save_data.set_defaults(func=save_data)
    p_save_data.add_argument("fname", help="filename to write to", nargs="?")
    p_save_data.add_argument(
        "--screen",
        "-s",
        action="store_true",
        help="read the data shown on the screen, rather than the whole memory",
    )
    p_save_data.add_argument(
        "-r",
        "--raw",
        help="don't convert to voltages before saving to reduce storage space",
    )
    # TODO
    # p_save_data.add_argument(
    #     "-t"
    #     "--time"
    #     help="write a time column to the file",
    # )

    p_save_data.add_argument(
        "-f",
        "--format",
        choices=write_formats.keys(),
        help=f"""format to write, automatically detected from fname if given;
            default: {default_write_format}
            """,
    )

    p_save_data.add_argument(
        "-c",
        "--channels",
        help="channels to save, comma-seperated names, e.g. '1', 'CHAN1', 'D0', 'MATH'",
    )

    return parser, parser.parse_args()


def main():
    try:
        parser, args = parse_args()
        args.func(args)
    except UserError as e:
        parser.error(str(e))


if __name__ == "__main__":
    main()
