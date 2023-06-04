import pyvisa
import dataclasses
from enum import Enum
from tqdm import tqdm
from typing import Any, Optional
import numpy as np
from .exceptions import UserError
from .resource import fixup_resource


class WavFormat(Enum):
    BYTE = 0
    WORD = 1
    ASC = 2


class WavType(Enum):
    NORM = 0
    MAX = 1
    RAW = 2

    NORMal = NORM
    MAXimum = MAX


@dataclasses.dataclass
class Preamble:
    format: WavFormat
    type: WavType
    points: int
    count: int
    xincrement: float
    xorigin: float
    xreference: int
    yincrement: float
    yorigin: float
    yreference: int

    @classmethod
    def parse(cls, preamble: str) -> "Preamble":
        parts = preamble.split(",")
        return cls(
            format=WavFormat(int(parts[0])),
            type=WavType(int(parts[1])),
            points=int(parts[2]),
            count=int(parts[3]),
            xincrement=float(parts[4]),
            xorigin=float(parts[5]),
            xreference=int(parts[6]),
            yincrement=float(parts[7]),
            yorigin=float(parts[8]),
            yreference=int(parts[9]),
        )


# channel to preamble and data
DataDict = dict[str, tuple[Preamble, np.ndarray]]


class DS1000Z:
    def __init__(self, resource: pyvisa.Resource):
        fixup_resource(resource)

        self.resource = resource

    def is_stopped(self) -> bool:
        return self.resource.query(":TRIGger:STATus?") == "STOP"

    def _get_preamble(self) -> Preamble:
        preamble = self.resource.query(":WAVeform:PREamble?")
        return Preamble.parse(preamble)

    @staticmethod
    def _parse_DATA(buf):
        assert buf[0:1] == b"#"

        assert 2 <= len(buf)
        n_digits = int(buf[1:2])

        assert 2 + n_digits <= len(buf)
        n_bytes = int(buf[2 : 2 + n_digits])

        start = 2 + n_digits
        end = start + n_bytes
        assert end <= len(buf)
        return buf[start:end]

    def _get_channel_data(self, stopped) -> tuple[Preamble, np.ndarray]:
        """get all data for the currently configured channel

        SOURce, FORMat and MODE must already have been set; only BYTE format is
        supported as there's no reason to use other formats
        """
        preamble = self._get_preamble()
        assert preamble.format == WavFormat.BYTE, "only byte reading is supported"

        max_byte_len = 250000

        buf = bytearray()

        for start in tqdm(range(0, preamble.points, max_byte_len), leave=False):
            self.resource.write(":WAVeform:STARt {0}".format(start + 1))
            stop = min(preamble.points, start + max_byte_len)
            self.resource.write(":WAVeform:STOP {0}".format(stop))

            self.resource.write(":WAVeform:DATA?")
            # 11 byte header plus newline
            chunk_buf = self.resource.read_bytes(stop - start + 12)
            chunk = self._parse_DATA(chunk_buf)
            buf.extend(chunk)

        return preamble, np.frombuffer(buf, np.uint8)

    def _set_wav_format(self, format: WavFormat):
        self.resource.write(f":WAVeform:FORMat {format.name}")

    def _set_wav_type(self, type: WavType):
        self.resource.write(f":WAVeform:MODE {type.name}")

    def _set_wav_source(self, source: str):
        """source should be D0-D15, CHAN1-CHAN4 or MATH"""
        self.resource.write(f":WAVeform:SOURce {source}")

    def _get_enabled_channels(self) -> list[str]:
        channels = []
        for i in range(1, 5):
            name = f"CHAN{i}"
            if int(self.resource.query(f":{name}:DISPlay?")):
                channels.append(name)

        return channels

    def _get_data(
        self, mode: WavType, channels: Optional[list[str]] = None
    ) -> DataDict:
        if channels is None:
            channels = self._get_enabled_channels()

        stopped = self.is_stopped()
        if not stopped and len(channels) > 1:
            raise UserError("scope must be stopped to read more than one channel")
        if not stopped and mode is WavType.RAW:
            raise UserError("scope must be stopped to read data memory")

        self._set_wav_type(mode)
        self._set_wav_format(WavFormat.BYTE)

        out = {}
        for channel in tqdm(channels):
            self._set_wav_source(channel)

            out[channel] = self._get_channel_data(stopped)
        return out

    def get_data_memory(self, channels: Optional[list[str]] = None) -> DataDict:
        return self._get_data(WavType.RAW, channels)

    def get_data_screen(self, channels: Optional[list[str]] = None) -> DataDict:
        return self._get_data(WavType.NORMal, channels)

    def get_screenshot(
        self, format: str = "PNG", color: bool = True, invert: bool = False
    ) -> bytes:
        """get a screen image"""

        def fmt_bool(b: bool) -> str:
            return "ON" if b else "OFF"

        self.resource.write(
            f":DISPlay:DATA? {fmt_bool(color)},{fmt_bool(invert)},{format}"
        )

        # read TMC-formatted data. it might be nice if this was merged with
        # _parse_DATA, but for data reading we already know how many bytes
        # we're going to get, and the docs say that N=9, so there's no reason
        # to add yet another round-trip

        hash_n = self.resource.read_bytes(2)
        assert len(hash_n) == 2
        assert hash_n[0:1] == b"#"

        n_digits = int(hash_n[1:2])

        n_bytes_str = self.resource.read_bytes(n_digits)
        assert len(n_bytes_str) == n_digits

        # +1 to consume newline
        return self.resource.read_bytes(int(n_bytes_str) + 1)[:-1]


def bytes_to_voltage(preamble: Preamble, data: np.ndarray) -> np.ndarray:
    """convert data bytes to voltages with aid of the preamble"""
    return (
        data.astype(np.float32) - preamble.yorigin - preamble.yreference
    ) * preamble.yincrement


def preamble_as_dict(preamble: Preamble) -> dict:
    """convert a preamble to a dictionary which can be unpickled without access
    to this module"""
    preamble_dict = dataclasses.asdict(preamble)
    preamble_dict["format"] = preamble_dict["format"].name
    preamble_dict["type"] = preamble_dict["type"].name
    return preamble_dict


def process_data(
    data: DataDict, to_voltage: bool = False, to_dict=False
) -> dict[str, Any]:
    """post-process the results of get_data_memory

    Parameters:
        to_voltage: convert bytes to float32 voltages
        to_dict: convert a preamble to a dictionary which can be unpickled
            without access to this module
    """
    if to_voltage:
        data = {c: (pre, bytes_to_voltage(pre, d)) for (c, (pre, d)) in data.items()}

    if to_dict:
        data = {c: (preamble_as_dict(pre), d) for (c, (pre, d)) in data.items()}  # type: ignore

    return data


if __name__ == "__main__":
    rm = pyvisa.ResourceManager()
    scope = DS1000Z(rm.open_resource("TCPIP::scope.lan::INSTR"))

    data = scope.get_data_memory()
    data = process_data(data, to_voltage=True, to_dict=True)
    np.save("out.npy", data)  # type: ignore
