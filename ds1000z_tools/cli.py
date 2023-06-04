from .exceptions import UserError
from .resource import DEFAULT_RESOURCE_PATTERN, DEFAULT_IDN_PATTERN


def connect(args):
    import pyvisa

    rm = pyvisa.ResourceManager(args.visa)

    name = args.name
    if args.address is not None:
        name = DEFAULT_RESOURCE_PATTERN.format(addr=args.address)

    if name is None:
        from .discover import discover

        res = discover(rm, DEFAULT_RESOURCE_PATTERN, DEFAULT_IDN_PATTERN)
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
    channels = parse_channels(args.channels)
    fname, format = get_fname_format(args)

    rm, scope = connect(args)

    if args.screen:
        data = scope.get_data_screen(channels)
    else:
        data = scope.get_data_memory(channels)

    from .scope import process_data

    data = process_data(data, to_voltage=not args.raw, to_dict=True)

    write_formats[format](fname, data)


def save_screen(args):
    from pathlib import Path

    fname = args.fname

    if fname is None:
        fname = auto_fname("png")
    else:
        if Path(fname).suffix.lstrip(".").lower() != "png":
            raise UserError("fname must end with .png")

    rm, scope = connect(args)

    data = scope.get_screenshot()
    with open(fname, "wb") as f:
        f.write(data)


def parse_args():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--visa",
        default="@py",
        help="pyvisa VISA implementation to use. default: %(default)s",
    )

    host_group = parser.add_mutually_exclusive_group()
    host_group.add_argument("--address", "-a", help="scope host name or IP")
    default_name_help = DEFAULT_RESOURCE_PATTERN.format(addr="address")
    host_group.add_argument(
        "--name",
        "-n",
        help=f"VISA resource name to connect to. default: {default_name_help}",
    )

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

    p_save_screen = subparsers.add_parser(
        "save-screen",
        help="save an image of the screen",
    )
    p_save_screen.set_defaults(func=save_screen)
    p_save_screen.add_argument("fname", help="filename to write to", nargs="?")

    return parser, parser.parse_args()


def main():
    try:
        parser, args = parse_args()
        args.func(args)
    except UserError as e:
        parser.error(str(e))


if __name__ == "__main__":
    main()
